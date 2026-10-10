"""Queue contracts and PostgreSQL crash/replay isolation tests."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import Connection, func, inspect, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.ai.errors import AIProviderError
from app.ai.extraction import FinancialNoteExtractor
from app.ai.mock import MockStructuredProvider
from app.ai.proposal_service import FinancialProposalService
from app.core.config import Settings
from app.core.logging import bind_request_id, current_request_id
from app.db.base import Base
from app.db.session import Database
from app.domain.enums import ProposalStatus
from app.jobs.config import JobsSettings
from app.jobs.repository import JobRepository, Lease
from app.jobs.schemas import EnqueueJob, FinancialNotePayload, JobError, JobStatus
from app.jobs.service import JobService
from app.jobs.worker import JobWorker, reconciliation_policy, retry_delay
from app.models import FinancialEventProposal, LedgerTransaction, User
from app.models.job import Job

TIMESTAMP = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)


def command(key: UUID | None = None, note: str = "Paid 249 for music") -> EnqueueJob:
    return EnqueueJob(
        kind="financial_note_extract",
        idempotency_key=key or uuid4(),
        payload=FinancialNotePayload(note=note, source_timestamp=TIMESTAMP),
    )


async def seed(database: Database) -> UUID:
    owner = uuid4()
    async with database.session_factory()() as session, session.begin():
        session.add(User(id=owner, email=f"{owner}@example.test", name="Jobs owner"))
    return owner


async def claim(database: Database, settings: JobsSettings) -> Lease | None:
    async with database.session_factory()() as session, session.begin():
        return await JobRepository(session, settings).claim()


async def expire(database: Database, job_id: UUID) -> None:
    async with database.session_factory()() as session, session.begin():
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )


async def make_ready(database: Database, job_id: UUID) -> None:
    async with database.session_factory()() as session, session.begin():
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(available_at=datetime.now(UTC) - timedelta(seconds=1))
        )


def proposal_service(database: Database) -> tuple[FinancialProposalService, MockStructuredProvider]:
    provider = MockStructuredProvider(
        [
            {
                "event_kind": "expense",
                "amount": "249.0000",
                "currency": "INR",
                "description": "Music subscription",
                "occurred_at": "2026-10-11T00:00:00+00:00",
                "merchant_name": "Example Music",
                "tags": [],
                "confidence": "0.9300",
            }
        ]
    )
    return FinancialProposalService(
        database,
        FinancialNoteExtractor(
            provider, max_input_chars=8000, review_confidence_threshold=Decimal("0.85")
        ),
    ), provider


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "arbitrary_python"},
        {"payload": {"note": "private", "source_timestamp": "2026-10-11T00:00:00"}},
        {"payload": {"note": " ", "source_timestamp": TIMESTAMP}},
        {"payload": {"note": "bad\x00note", "source_timestamp": TIMESTAMP}},
        {"payload": {"note": "x" * 8001, "source_timestamp": TIMESTAMP}},
        {"payload": {"note": "😀" * 8000, "source_timestamp": TIMESTAMP}},
        {"payload": {"note": "x", "source_timestamp": TIMESTAMP, "labels": ["a"] * 13}},
        {"payload": {"note": "x", "source_timestamp": TIMESTAMP, "labels": ["a" * 41]}},
        {"payload": {"note": "x", "source_timestamp": TIMESTAMP, "task": "exec"}},
    ],
)
def test_allowlist_and_payload_limits(overrides: dict[str, object]) -> None:
    values = command().model_dump()
    values.update(overrides)
    with pytest.raises(ValidationError):
        EnqueueJob.model_validate(values)


def test_limits_and_backoff() -> None:
    with pytest.raises(ValidationError):
        JobsSettings(concurrency=17)
    with pytest.raises(ValidationError):
        JobsSettings(lease_seconds=120, timeout_seconds=120)
    settings = JobsSettings(backoff_seconds=2, max_backoff_seconds=10)
    assert retry_delay(1, settings, 0) == 1
    assert retry_delay(2, settings, 1) == 4
    assert retry_delay(5, settings, 1) == 10
    assert command().fingerprint() == command(command().idempotency_key).fingerprint()


def test_worker_reconciliation_settings(test_settings: Settings) -> None:
    settings = test_settings.model_copy(
        update={
            "reconciliation_candidate_window_minutes": 320,
            "reconciliation_max_candidates": 12,
            "reconciliation_possible_duplicate_threshold": Decimal("0.60"),
            "reconciliation_auto_merge_threshold": Decimal("0.95"),
            "reconciliation_amount_weight": Decimal("0.40"),
            "reconciliation_time_weight": Decimal("0.20"),
            "reconciliation_merchant_weight": Decimal("0.15"),
            "reconciliation_description_weight": Decimal("0.25"),
        }
    )
    policy = reconciliation_policy(settings)
    assert policy.candidate_window_minutes == 320
    assert policy.max_candidates == 12
    assert policy.possible_duplicate_threshold == Decimal("0.60")
    assert policy.auto_merge_threshold == Decimal("0.95")
    assert policy.amount_weight == Decimal("0.40")
    assert policy.time_weight == Decimal("0.20")
    assert policy.merchant_weight == Decimal("0.15")
    assert policy.description_weight == Decimal("0.25")


@pytest.mark.database
async def test_owner_idempotency_conflict_backpressure_and_redaction(
    isolated_database: Database,
) -> None:
    owner, other = await seed(isolated_database), await seed(isolated_database)
    service = JobService(isolated_database, JobsSettings(max_pending_per_owner=1))
    request = command()
    first = await service.enqueue(owner, request)
    assert await service.enqueue(owner, request) == first
    assert "payload" not in first.model_dump()
    with pytest.raises(JobError, match="IDEMPOTENCY_CONFLICT"):
        await service.enqueue(owner, command(request.idempotency_key, "Different note"))
    with pytest.raises(JobError, match="OWNER_JOB_LIMIT"):
        await service.enqueue(owner, command())
    assert (await service.enqueue(other, request)).id != first.id
    for operation in (service.get, service.retry, service.cancel):
        with pytest.raises(JobError, match="JOB_NOT_FOUND"):
            await operation(other, first.id)
    assert len(await service.list(owner)) == 1
    assert await service.list(owner, status=JobStatus.DEAD_LETTER) == []


@pytest.mark.database
async def test_concurrent_replay_and_global_capacity(isolated_database: Database) -> None:
    owner = await seed(isolated_database)
    settings = JobsSettings(max_pending=2)
    service = JobService(isolated_database, settings)
    request = command()
    results = await asyncio.gather(*(service.enqueue(owner, request) for _ in range(6)))
    assert len({job.id for job in results}) == 1
    await service.enqueue(owner, command())
    with pytest.raises(JobError, match="JOB_QUEUE_FULL"):
        await service.enqueue(await seed(isolated_database), command())


@pytest.mark.database
async def test_bounded_concurrent_claims_and_skip_locked(isolated_database: Database) -> None:
    owner = await seed(isolated_database)
    settings = JobsSettings(concurrency=2)
    service = JobService(isolated_database, settings)
    jobs = [await service.enqueue(owner, command()) for _ in range(3)]
    async with isolated_database.session_factory()() as lock_session, lock_session.begin():
        await lock_session.scalar(select(Job).where(Job.id == jobs[0].id).with_for_update())
        leases = await asyncio.gather(*(claim(isolated_database, settings) for _ in range(3)))
    obtained = [lease for lease in leases if lease is not None]
    assert len(obtained) == 2
    assert len({lease.id for lease in obtained}) == 2
    assert jobs[0].id not in {lease.id for lease in obtained}
    assert await claim(isolated_database, settings) is None


@pytest.mark.database
async def test_lease_recovery_fences_old_completion(isolated_database: Database) -> None:
    owner = await seed(isolated_database)
    settings = JobsSettings()
    service = JobService(isolated_database, settings)
    job = await service.enqueue(owner, command())
    old = await claim(isolated_database, settings)
    assert old is not None
    await expire(isolated_database, job.id)
    assert await claim(isolated_database, settings) is None
    assert (await service.get(owner, job.id)).status == JobStatus.RETRY_WAIT
    await make_ready(isolated_database, job.id)
    new = await claim(isolated_database, settings)
    assert new is not None and new.token != old.token and new.attempts == 2
    async with isolated_database.session_factory()() as session, session.begin():
        repository = JobRepository(session, settings)
        assert not await repository.finish(old, result={"proposal_id": str(uuid4())})
        assert await repository.finish(new, result={"proposal_id": str(uuid4())})
    assert (await service.get(owner, job.id)).status == JobStatus.SUCCEEDED


@pytest.mark.database
async def test_dead_letter_review_limit_and_reliable_cancellation(
    isolated_database: Database,
) -> None:
    owner = await seed(isolated_database)
    settings = JobsSettings(max_attempts=1)
    service = JobService(isolated_database, settings)
    job = await service.enqueue(owner, command())
    for review in range(4):
        assert await claim(isolated_database, settings) is not None
        with pytest.raises(JobError, match="JOB_CANNOT_CANCEL"):
            await service.cancel(owner, job.id)
        await expire(isolated_database, job.id)
        assert await claim(isolated_database, settings) is None
        dead = await service.get(owner, job.id)
        assert dead.status == JobStatus.DEAD_LETTER
        assert dead.review_retries == review
        if review < 3:
            await service.retry(owner, job.id)
    with pytest.raises(JobError, match="JOB_NOT_RETRYABLE"):
        await service.retry(owner, job.id)
    queued = await service.enqueue(owner, command())
    cancelled = await service.cancel(owner, queued.id)
    assert cancelled.status == JobStatus.CANCELLED
    assert await service.cancel(owner, queued.id) == cancelled
    assert await claim(isolated_database, settings) is None


@pytest.mark.database
async def test_crash_after_proposal_commit_replays_without_duplicate_extraction(
    isolated_database: Database,
) -> None:
    owner = await seed(isolated_database)
    settings = JobsSettings()
    service = JobService(isolated_database, settings)
    job = await service.enqueue(owner, command())
    proposals, provider = proposal_service(isolated_database)
    lease = await claim(isolated_database, settings)
    assert lease is not None
    payload = FinancialNotePayload.model_validate(lease.payload)
    committed = await proposals.submit_manual_note(
        owner,
        note=payload.note,
        source_timestamp=payload.source_timestamp,
        client_request_id=lease.id,
        labels=payload.labels,
    )
    # Simulate death between proposal commit and fenced queue completion.
    await expire(isolated_database, job.id)
    await claim(isolated_database, settings)
    await make_ready(isolated_database, job.id)
    assert await JobWorker(isolated_database, proposals, settings).run_once()
    finished = await service.get(owner, job.id)
    assert finished.status == JobStatus.SUCCEEDED
    assert finished.result is not None and finished.result.proposal_id == committed.id
    assert len(provider.requests) == 1
    assert (await proposals.list(owner))[0].status == ProposalStatus.NEEDS_REVIEW
    async with isolated_database.session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(FinancialEventProposal)) == 1
        assert await session.scalar(select(func.count()).select_from(LedgerTransaction)) == 0
        assert (await session.scalars(select(Job.payload))).one() == {}


@pytest.mark.database
async def test_worker_capped_retries_and_content_safe_errors(
    isolated_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await seed(isolated_database)
    settings = JobsSettings(max_attempts=2)
    service = JobService(isolated_database, settings)
    job = await service.enqueue(owner, command())
    proposals, _ = proposal_service(isolated_database)
    failure = AsyncMock(
        side_effect=AIProviderError(
            code="UPSTREAM_SECRET", message="private financial note and secret endpoint"
        )
    )
    monkeypatch.setattr(proposals, "submit_manual_note", failure)
    worker = JobWorker(isolated_database, proposals, settings)
    assert await worker.run_once()
    waiting = await service.get(owner, job.id)
    assert waiting.status == JobStatus.RETRY_WAIT
    assert waiting.attempts == 1
    assert waiting.error_code == "PROVIDER_UNAVAILABLE"
    assert "private" not in waiting.model_dump_json()
    assert not await worker.run_once()
    await make_ready(isolated_database, job.id)
    assert await worker.run_once()
    dead = await service.get(owner, job.id)
    assert dead.status == JobStatus.DEAD_LETTER
    assert dead.attempts == 2
    assert not await worker.run_once()
    assert failure.await_count == 2


@pytest.mark.database
async def test_worker_disabled_provider_dead_letters_immediately(
    isolated_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await seed(isolated_database)
    settings = JobsSettings()
    service = JobService(isolated_database, settings)
    job = await service.enqueue(owner, command())
    proposals, _ = proposal_service(isolated_database)
    monkeypatch.setattr(
        proposals,
        "submit_manual_note",
        AsyncMock(side_effect=AIProviderError(code="AI_PROVIDER_DISABLED", message="disabled")),
    )
    assert await JobWorker(isolated_database, proposals, settings).run_once()
    dead = await service.get(owner, job.id)
    assert dead.status == JobStatus.DEAD_LETTER and dead.attempts == 1
    assert dead.error_code == "AI_PROVIDER_DISABLED"


@pytest.mark.database
async def test_jobs_migration_upgrade_and_downgrade(isolated_database: Database) -> None:
    migration = import_module("migrations.versions.20261011_0009_jobs")
    assert migration.down_revision == "20261011_0008"

    def upgrade(connection: Connection) -> None:
        Base.metadata.tables["jobs"].drop(connection)
        with Operations.context(
            MigrationContext.configure(
                connection,
                opts={"target_metadata": Base.metadata},
            )
        ):
            migration.upgrade()
        assert {column["name"] for column in inspect(connection).get_columns("jobs")} == {
            column.name for column in Job.__table__.columns
        }

    async with isolated_database.engine().begin() as connection:
        await connection.run_sync(upgrade)
    owner = await seed(isolated_database)
    settings = JobsSettings()
    service = JobService(isolated_database, settings)
    job = await service.enqueue(owner, command())
    assert (await service.cancel(owner, job.id)).status == JobStatus.CANCELLED

    def downgrade(connection: Connection) -> None:
        with Operations.context(
            MigrationContext.configure(
                connection,
                opts={"target_metadata": Base.metadata},
            )
        ):
            migration.downgrade()
        assert not inspect(connection).has_table("jobs")

    async with isolated_database.engine().begin() as connection:
        await connection.run_sync(downgrade)


@pytest.mark.database
async def test_worker_database_failure_safe_logs_and_correlation_reset(
    isolated_database: Database,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    owner = await seed(isolated_database)
    settings = JobsSettings()
    service = JobService(isolated_database, settings)
    job = await service.enqueue(owner, command())
    proposals, _ = proposal_service(isolated_database)
    monkeypatch.setattr(
        proposals,
        "submit_manual_note",
        AsyncMock(
            side_effect=SQLAlchemyError("private note secret SQL parameters"),
        ),
    )
    caplog.set_level(logging.INFO, logger="app.jobs.worker")
    token = bind_request_id("outer-request")
    try:
        assert await JobWorker(isolated_database, proposals, settings).run_once()
        assert current_request_id() == "outer-request"
    finally:
        token.var.reset(token)
    waiting = await service.get(owner, job.id)
    assert waiting.status == JobStatus.RETRY_WAIT
    assert waiting.error_code == "JOB_DATABASE_ERROR"
    records = [record for record in caplog.records if record.name == "app.jobs.worker"]
    assert [record.getMessage() for record in records] == [
        "job.claimed",
        "job.error",
        "job.completed",
    ]
    for record in records:
        assert record.__dict__["job_id"] == str(job.id)
        assert record.__dict__["request_id"] == str(job.id)
        assert "private" not in str(record.__dict__)
    assert records[1].__dict__["error_type"] == "SQLAlchemyError"


@pytest.mark.database
async def test_unknown_programmer_fault_fails_worker_task(
    isolated_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await seed(isolated_database)
    settings = JobsSettings(concurrency=1)
    service = JobService(isolated_database, settings)
    job = await service.enqueue(owner, command())
    proposals, _ = proposal_service(isolated_database)
    monkeypatch.setattr(
        proposals,
        "submit_manual_note",
        AsyncMock(
            side_effect=RuntimeError("programmer bug"),
        ),
    )
    worker = JobWorker(isolated_database, proposals, settings)
    with pytest.raises(ExceptionGroup) as failure:
        await worker.run(asyncio.Event())
    assert isinstance(failure.value.exceptions[0], RuntimeError)
    assert (await service.get(owner, job.id)).status == JobStatus.RUNNING


@pytest.mark.database
async def test_worker_stale_lease_emits_event_without_overwriting(
    isolated_database: Database,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    owner = await seed(isolated_database)
    settings = JobsSettings()
    service = JobService(isolated_database, settings)
    job = await service.enqueue(owner, command())
    lease = await claim(isolated_database, settings)
    assert lease is not None
    await expire(isolated_database, job.id)
    proposals, _ = proposal_service(isolated_database)
    monkeypatch.setattr(
        proposals,
        "submit_manual_note",
        AsyncMock(
            side_effect=SQLAlchemyError("private"),
        ),
    )
    caplog.set_level(logging.INFO, logger="app.jobs.worker")
    await JobWorker(isolated_database, proposals, settings).execute(lease)
    assert (await service.get(owner, job.id)).status == JobStatus.RUNNING
    assert "job.stale_lease" in caplog.messages
