"""Short queue transactions with bounded admission, SKIP LOCKED and fencing."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.config import JobsSettings
from app.jobs.schemas import EnqueueJob, JobError, JobView
from app.models.job import Job

ACTIVE = ("queued", "running", "retry_wait")
# All API/worker replicas must share the same limits and admission lock.
ADMISSION_LOCK = 739_491_009


@dataclass(frozen=True)
class Lease:
    id: UUID
    user_id: UUID
    token: UUID
    payload: dict[str, Any]
    attempts: int


class JobRepository:
    def __init__(self, session: AsyncSession, settings: JobsSettings) -> None:
        self.session = session
        self.settings = settings

    async def admission_lock(self) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADMISSION_LOCK}
        )

    async def now(self) -> datetime:
        value = await self.session.scalar(select(func.clock_timestamp()))
        assert isinstance(value, datetime)
        return value

    async def get(self, owner: UUID, job_id: UUID, *, lock: bool = False) -> Job | None:
        query = select(Job).where(Job.user_id == owner, Job.id == job_id)
        if lock:
            query = query.with_for_update()
        return cast(Job | None, await self.session.scalar(query))

    async def check_capacity(self, owner: UUID) -> None:
        total = await self.session.scalar(
            select(func.count()).select_from(Job).where(Job.status.in_(ACTIVE))
        )
        owned = await self.session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status.in_(ACTIVE), Job.user_id == owner)
        )
        if (total or 0) >= self.settings.max_pending:
            raise JobError("JOB_QUEUE_FULL", 429)
        if (owned or 0) >= self.settings.max_pending_per_owner:
            raise JobError("OWNER_JOB_LIMIT", 429)

    async def enqueue(self, owner: UUID, command: EnqueueJob) -> JobView:
        await self.admission_lock()
        existing = await self.session.scalar(
            select(Job).where(Job.user_id == owner, Job.idempotency_key == command.idempotency_key)
        )
        if existing is not None:
            if existing.payload_hash != command.fingerprint():
                raise JobError("IDEMPOTENCY_CONFLICT", 409)
            return JobView.model_validate(existing)
        await self.check_capacity(owner)
        job = Job(
            user_id=owner,
            idempotency_key=command.idempotency_key,
            kind=command.kind,
            payload=command.payload.model_dump(mode="json"),
            payload_hash=command.fingerprint(),
            available_at=await self.now(),
            max_attempts=self.settings.max_attempts,
        )
        self.session.add(job)
        await self.session.flush()
        return JobView.model_validate(job)

    async def claim(self) -> Lease | None:
        await self.admission_lock()
        now = await self.now()
        # Recovery is atomic with admission. Expired tokens can never finish a new lease.
        await self.session.execute(
            update(Job)
            .where(Job.status == "running", Job.lease_expires_at <= now)
            .values(
                status="dead_letter",
                error_code="LEASE_EXPIRED",
                lease_token=None,
                lease_expires_at=None,
                completed_at=now,
            )
            .where(Job.attempts >= Job.max_attempts)
        )
        await self.session.execute(
            update(Job)
            .where(
                Job.status == "running",
                Job.lease_expires_at <= now,
                Job.attempts < Job.max_attempts,
            )
            .values(
                status="retry_wait",
                error_code="LEASE_EXPIRED",
                lease_token=None,
                lease_expires_at=None,
                available_at=func.clock_timestamp()
                + func.make_interval(
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    func.least(
                        self.settings.max_backoff_seconds,
                        self.settings.backoff_seconds * func.power(2, Job.attempts - 1),
                    )
                    * (0.5 + 0.5 * func.random()),
                ),
            )
        )
        running = await self.session.scalar(
            select(func.count()).select_from(Job).where(Job.status == "running")
        )
        if (running or 0) >= self.settings.concurrency:
            return None
        job = await self.session.scalar(
            select(Job)
            .where(
                or_(Job.status == "queued", Job.status == "retry_wait"),
                Job.available_at <= now,
                Job.attempts < Job.max_attempts,
            )
            .order_by(Job.available_at, Job.created_at, Job.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.lease_token = uuid4()
        job.lease_expires_at = now + timedelta(seconds=self.settings.lease_seconds)
        job.completed_at = None
        return Lease(job.id, job.user_id, job.lease_token, dict(job.payload), job.attempts)

    async def finish(
        self,
        lease: Lease,
        *,
        result: dict[str, str] | None = None,
        error_code: str | None = None,
        retryable: bool = False,
        delay_seconds: float = 0,
    ) -> bool:
        now = await self.now()
        job = await self.session.scalar(
            select(Job)
            .where(
                Job.id == lease.id,
                Job.user_id == lease.user_id,
                Job.status == "running",
                Job.lease_token == lease.token,
                Job.lease_expires_at > now,
            )
            .with_for_update()
        )
        if job is None:
            return False
        job.lease_token = None
        job.lease_expires_at = None
        job.error_code = error_code
        if result is not None:
            job.status = "succeeded"
            job.result = result
            job.completed_at = now
            # Raw events already retain the evidence; avoid a second durable note copy.
            job.payload = {}
        elif retryable and job.attempts < job.max_attempts:
            job.status = "retry_wait"
            job.available_at = now + timedelta(seconds=delay_seconds)
        else:
            job.status = "dead_letter"
            job.completed_at = now
        return True

    async def review_retry(self, owner: UUID, job_id: UUID) -> JobView:
        await self.admission_lock()
        job = await self.get(owner, job_id, lock=True)
        if job is None:
            raise JobError("JOB_NOT_FOUND", 404)
        if job.status != "dead_letter" or job.review_retries >= 3:
            raise JobError("JOB_NOT_RETRYABLE", 409)
        await self.check_capacity(owner)
        job.status = "queued"
        job.attempts = 0
        job.review_retries += 1
        job.available_at = await self.now()
        job.completed_at = None
        job.error_code = None
        await self.session.flush()
        await self.session.refresh(job, attribute_names=["updated_at"])
        return JobView.model_validate(job)

    async def cancel(self, owner: UUID, job_id: UUID) -> JobView:
        job = await self.get(owner, job_id, lock=True)
        if job is None:
            raise JobError("JOB_NOT_FOUND", 404)
        if job.status == "cancelled":
            return JobView.model_validate(job)
        if job.status not in ("queued", "retry_wait"):
            raise JobError("JOB_CANNOT_CANCEL", 409)
        job.status = "cancelled"
        job.completed_at = await self.now()
        job.payload = {}
        await self.session.flush()
        await self.session.refresh(job, attribute_names=["updated_at"])
        return JobView.model_validate(job)
