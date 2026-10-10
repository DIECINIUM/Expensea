"""Run ``python -m app.jobs.worker`` after migrating the shared PostgreSQL database."""

import asyncio
import logging
import random
import signal
from contextlib import suppress
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.ai.errors import AIOutputError, AIProviderError, ProposalReviewError
from app.ai.extraction import FinancialNoteExtractor
from app.ai.factory import create_structured_provider
from app.ai.proposal_service import FinancialProposalService
from app.core.config import Settings, get_settings
from app.core.logging import bind_request_id, configure_logging, current_request_id
from app.db.session import Database
from app.ingestion.errors import ConnectorContentError
from app.jobs.config import JobsSettings
from app.jobs.repository import JobRepository, Lease
from app.jobs.schemas import FinancialNotePayload
from app.reconciliation.policy import ReconciliationPolicy

logger = logging.getLogger(__name__)


def reconciliation_policy(settings: Settings) -> ReconciliationPolicy:
    return ReconciliationPolicy(
        candidate_window_minutes=settings.reconciliation_candidate_window_minutes,
        max_candidates=settings.reconciliation_max_candidates,
        possible_duplicate_threshold=settings.reconciliation_possible_duplicate_threshold,
        auto_merge_threshold=settings.reconciliation_auto_merge_threshold,
        amount_weight=settings.reconciliation_amount_weight,
        time_weight=settings.reconciliation_time_weight,
        merchant_weight=settings.reconciliation_merchant_weight,
        description_weight=settings.reconciliation_description_weight,
    )


def event(
    name: str,
    lease: Lease | None = None,
    *,
    error_type: str | None = None,
    error_code: str | None = None,
) -> None:
    logger.log(
        logging.WARNING if error_type or error_code else logging.INFO,
        name,
        extra={
            "job_id": str(lease.id) if lease else None,
            "request_id": current_request_id(),
            "error_type": error_type,
            "error_code": error_code,
        },
    )


def retry_delay(attempt: int, settings: JobsSettings, jitter: float | None = None) -> float:
    """Equal jitter prevents lockstep recovery while preserving a bounded delay."""
    ceiling = min(
        settings.max_backoff_seconds, settings.backoff_seconds * 2 ** min(attempt - 1, 10)
    )
    return float(ceiling * (0.5 + 0.5 * (random.random() if jitter is None else jitter)))


class JobWorker:
    def __init__(
        self,
        database: Database,
        proposals: FinancialProposalService,
        settings: JobsSettings,
    ) -> None:
        self.database = database
        self.proposals = proposals
        self.settings = settings

    async def run_once(self) -> bool:
        async with self.database.session_factory()() as session, session.begin():
            lease = await JobRepository(session, self.settings).claim()
        if lease is None:
            return False
        await self.execute(lease)
        return True

    async def execute(self, lease: Lease) -> None:
        token = bind_request_id(str(lease.id))
        try:
            event("job.claimed", lease)
            await self._execute(lease)
        except SQLAlchemyError as exc:
            event("job.queue_error", lease, error_type=type(exc).__name__)
            raise
        finally:
            token.var.reset(token)

    async def _execute(self, lease: Lease) -> None:
        result: dict[str, str] | None = None
        error_code: str | None = None
        error_type: str | None = None
        retryable = False
        try:
            payload = FinancialNotePayload.model_validate(lease.payload)
            async with asyncio.timeout(self.settings.timeout_seconds):
                # Both identity and timestamp are persisted at enqueue. A crash after proposal
                # commit replays the same raw/prompt unique key, never a new canonical write.
                proposal = await self.proposals.submit_manual_note(
                    lease.user_id,
                    note=payload.note,
                    source_timestamp=payload.source_timestamp,
                    client_request_id=lease.id,
                    labels=payload.labels,
                )
            result = {"proposal_id": str(proposal.id)}
        except AIProviderError as exc:
            error_type = type(exc).__name__
            error_code = (
                "AI_PROVIDER_DISABLED"
                if exc.code == "AI_PROVIDER_DISABLED"
                else "PROVIDER_UNAVAILABLE"
            )
            retryable = exc.code != "AI_PROVIDER_DISABLED"
        except (AIOutputError, ProposalReviewError, ConnectorContentError) as exc:
            error_type = type(exc).__name__
            error_code = "EXTRACTION_REVIEW_REQUIRED"
        except ValidationError as exc:
            error_type = type(exc).__name__
            error_code = "INVALID_JOB_PAYLOAD"
        except TimeoutError as exc:
            error_type = type(exc).__name__
            error_code = "JOB_TIMEOUT"
            retryable = True
        except SQLAlchemyError as exc:
            error_type = type(exc).__name__
            error_code = "JOB_DATABASE_ERROR"
            retryable = True
        if error_code:
            event("job.error", lease, error_type=error_type, error_code=error_code)
        async with self.database.session_factory()() as session, session.begin():
            completed = await JobRepository(session, self.settings).finish(
                lease,
                result=result,
                error_code=error_code,
                retryable=retryable,
                delay_seconds=retry_delay(lease.attempts, self.settings),
            )
        event("job.completed" if completed else "job.stale_lease", lease, error_code=error_code)

    async def run(self, stop: asyncio.Event) -> None:
        async def slot() -> None:
            failures = 0
            while not stop.is_set():
                try:
                    worked = await self.run_once()
                    failures = 0
                except SQLAlchemyError as exc:
                    worked = False
                    failures = min(failures + 1, 5)
                    event("job.queue_unavailable", error_type=type(exc).__name__)
                if not worked:
                    with suppress(TimeoutError):
                        await asyncio.wait_for(
                            stop.wait(),
                            timeout=min(self.settings.poll_seconds * 2**failures, 30),
                        )

        async with asyncio.TaskGroup() as tasks:
            for _ in range(self.settings.concurrency):
                tasks.create_task(slot())


async def main() -> None:
    settings = get_settings()
    job_settings = JobsSettings()
    configure_logging(settings.log_level.value)
    database = Database(settings.database_url)
    proposals = FinancialProposalService(
        database,
        FinancialNoteExtractor(
            create_structured_provider(settings),
            max_input_chars=settings.ai_max_input_chars,
            review_confidence_threshold=Decimal(str(settings.ai_review_confidence_threshold)),
        ),
        reconciliation_policy=reconciliation_policy(settings),
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await JobWorker(database, proposals, job_settings).run(stop)
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
