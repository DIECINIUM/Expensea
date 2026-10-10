"""Owner-scoped operations on durable jobs."""

from uuid import UUID

from sqlalchemy import func, select

from app.db.session import Database
from app.jobs.config import JobsSettings
from app.jobs.repository import JobRepository
from app.jobs.schemas import EnqueueJob, JobError, JobStatus, JobView, QueueSnapshot
from app.models.job import Job


class JobService:
    def __init__(self, database: Database, settings: JobsSettings) -> None:
        self.database = database
        self.settings = settings

    async def enqueue(self, owner: UUID, command: EnqueueJob) -> JobView:
        async with self.database.session_factory()() as session, session.begin():
            return await JobRepository(session, self.settings).enqueue(owner, command)

    async def get(self, owner: UUID, job_id: UUID) -> JobView:
        async with self.database.session_factory()() as session:
            job = await JobRepository(session, self.settings).get(owner, job_id)
            if job is None:
                raise JobError("JOB_NOT_FOUND", 404)
            return JobView.model_validate(job)

    async def list(
        self, owner: UUID, *, status: JobStatus | None = None, limit: int = 20
    ) -> list[JobView]:
        if not 1 <= limit <= 50:
            raise JobError("INVALID_JOB_LIMIT", 422)
        query = select(Job).where(Job.user_id == owner)
        if status is not None:
            query = query.where(Job.status == status.value)
        async with self.database.session_factory()() as session:
            jobs = await session.scalars(query.order_by(Job.created_at.desc(), Job.id).limit(limit))
            return [JobView.model_validate(job) for job in jobs]

    async def retry(self, owner: UUID, job_id: UUID) -> JobView:
        async with self.database.session_factory()() as session, session.begin():
            return await JobRepository(session, self.settings).review_retry(owner, job_id)

    async def cancel(self, owner: UUID, job_id: UUID) -> JobView:
        async with self.database.session_factory()() as session, session.begin():
            return await JobRepository(session, self.settings).cancel(owner, job_id)

    async def snapshot(self, owner: UUID) -> QueueSnapshot:
        async with self.database.session_factory()() as session:
            rows = await session.execute(
                select(Job.status, func.count()).where(Job.user_id == owner).group_by(Job.status)
            )
            counts = {status: count for status, count in rows}
        return QueueSnapshot(
            **counts,
            pending_limit=self.settings.max_pending_per_owner,
            max_attempts=self.settings.max_attempts,
        )
