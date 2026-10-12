"""Authenticated, bounded REST enqueue/status/review endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from app.auth.dependencies import authenticate_request, require_csrf
from app.db.session import database_from_request
from app.jobs.config import JobsSettings
from app.jobs.schemas import (
    MAX_REQUEST_BYTES,
    EnqueueJob,
    JobError,
    JobStatus,
    JobView,
    QueueSnapshot,
)
from app.jobs.service import JobService


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(no_store)])


def service(request: Request) -> JobService:
    settings = getattr(request.app.state, "jobs_settings", None)
    if not isinstance(settings, JobsSettings):
        settings = JobsSettings()
    return JobService(database_from_request(request), settings)


def public_error(exc: JobError) -> HTTPException:
    return HTTPException(
        exc.status_code,
        detail={"code": exc.code},
        headers={"Retry-After": "5"} if exc.status_code == 429 else None,
    )


@router.post("", status_code=202)
async def enqueue(request: Request) -> JobView:
    principal = await authenticate_request(request)
    await require_csrf(request)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, detail={"code": "JOB_PAYLOAD_TOO_LARGE"})
        body.extend(chunk)
    try:
        command = EnqueueJob.model_validate_json(body)
    except ValidationError as exc:
        # Pydantic errors otherwise echo private input and note contents.
        raise HTTPException(422, detail={"code": "INVALID_JOB_PAYLOAD"}) from exc
    try:
        return await service(request).enqueue(principal.user_id, command)
    except JobError as exc:
        raise public_error(exc) from exc


@router.get("")
async def list_jobs(
    request: Request,
    status: JobStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[JobView]:
    principal = await authenticate_request(request)
    return await service(request).list(principal.user_id, status=status, limit=limit)


@router.get("/snapshot")
async def queue_snapshot(request: Request) -> QueueSnapshot:
    principal = await authenticate_request(request)
    return await service(request).snapshot(principal.user_id)


@router.get("/{job_id}")
async def get_job(request: Request, job_id: UUID) -> JobView:
    principal = await authenticate_request(request)
    try:
        return await service(request).get(principal.user_id, job_id)
    except JobError as exc:
        raise public_error(exc) from exc


@router.post("/{job_id}/retry")
async def retry_job(request: Request, job_id: UUID) -> JobView:
    principal = await authenticate_request(request)
    await require_csrf(request)
    try:
        return await service(request).retry(principal.user_id, job_id)
    except JobError as exc:
        raise public_error(exc) from exc


@router.post("/{job_id}/cancel")
async def cancel_job(request: Request, job_id: UUID) -> JobView:
    principal = await authenticate_request(request)
    await require_csrf(request)
    try:
        return await service(request).cancel(principal.user_id, job_id)
    except JobError as exc:
        raise public_error(exc) from exc
