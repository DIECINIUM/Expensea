"""REST validation authenticates first and never echoes note content."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.auth.principal import Principal
from app.auth.session import SESSION_COOKIE, digest
from app.core.config import Settings
from app.db.session import Database
from app.jobs import routes
from app.jobs.config import JobsSettings
from app.models import User
from app.models.auth import AuthSession


@pytest.fixture
async def jobs_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    app = FastAPI()
    app.include_router(routes.router)
    authenticate = AsyncMock(return_value=Principal(user_id=uuid4()))
    monkeypatch.setattr(routes, "authenticate_request", authenticate)
    monkeypatch.setattr(routes, "require_csrf", AsyncMock())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    assert authenticate.await_count > 0


async def test_invalid_request_does_not_echo_private_note(jobs_client: httpx.AsyncClient) -> None:
    response = await jobs_client.post(
        "/api/jobs",
        json={
            "kind": "exec",
            "idempotency_key": str(uuid4()),
            "payload": {"note": "private account information"},
        },
    )
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "INVALID_JOB_PAYLOAD"}}
    assert "private" not in response.text


async def test_oversized_request_is_rejected(jobs_client: httpx.AsyncClient) -> None:
    response = await jobs_client.post("/api/jobs", content="x" * 32769)
    assert response.status_code == 413
    assert response.json() == {"detail": {"code": "JOB_PAYLOAD_TOO_LARGE"}}


@pytest.mark.database
async def test_rest_owner_status_idempotency_and_backpressure(
    isolated_database: Database,
    test_settings: Settings,
) -> None:
    owner, other = uuid4(), uuid4()
    async with isolated_database.session_factory()() as session, session.begin():
        session.add_all(
            [
                User(id=owner, email=f"{owner}@example.test", name="Owner"),
                User(id=other, email=f"{other}@example.test", name="Other"),
            ]
        )
    app = FastAPI()
    app.state.database = isolated_database
    app.state.settings = test_settings.model_copy(update={"dev_user_id": owner})
    app.state.jobs_settings = JobsSettings(max_pending_per_owner=1)
    app.include_router(routes.router)
    request = {
        "kind": "financial_note_extract",
        "idempotency_key": str(uuid4()),
        "payload": {
            "note": "private financial note",
            "source_timestamp": "2026-10-11T00:00:00Z",
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/api/jobs", json=request)
        assert first.status_code == 202
        job_id = first.json()["id"]
        assert (await client.post("/api/jobs", json=request)).json() == first.json()
        assert "private" not in first.text
        status = await client.get(f"/api/jobs/{job_id}")
        assert status.status_code == 200 and status.json()["status"] == "queued"
        assert status.headers["cache-control"] == "no-store"
        snapshot = await client.get("/api/jobs/snapshot")
        assert snapshot.status_code == 200
        assert snapshot.json()["queued"] == 1
        assert snapshot.json()["pending_limit"] == 1
        assert snapshot.headers["cache-control"] == "no-store"
        request["idempotency_key"] = str(uuid4())
        full = await client.post("/api/jobs", json=request)
        assert full.status_code == 429 and full.headers["retry-after"] == "5"
        app.state.settings = test_settings.model_copy(update={"dev_user_id": other})
        assert (await client.get("/api/jobs")).json() == []
        assert (await client.get("/api/jobs/snapshot")).json()["queued"] == 0
        assert (await client.get(f"/api/jobs/{job_id}")).status_code == 404
        assert (await client.post(f"/api/jobs/{job_id}/retry")).status_code == 404
        assert (await client.post(f"/api/jobs/{job_id}/cancel")).status_code == 404
        app.state.settings = test_settings.model_copy(update={"dev_user_id": owner})
        cancelled = await client.post(f"/api/jobs/{job_id}/cancel")
        assert cancelled.json()["status"] == "cancelled"


@pytest.mark.database
async def test_cookie_authenticated_enqueue_requires_session_csrf_and_origin(
    isolated_database: Database,
    test_settings: Settings,
) -> None:
    owner = uuid4()
    async with isolated_database.session_factory()() as session, session.begin():
        session.add(User(id=owner, email=f"{owner}@example.test", name="Owner"))
        await session.flush()
        session.add(
            AuthSession(
                token_hash=digest("opaque-session"),
                user_id=owner,
                csrf_token="session-csrf",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    app = FastAPI()
    app.state.database = isolated_database
    app.state.settings = test_settings
    app.include_router(routes.router)
    request = {
        "kind": "financial_note_extract",
        "idempotency_key": str(uuid4()),
        "payload": {"note": "Private", "source_timestamp": "2026-10-11T00:00:00Z"},
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={SESSION_COOKIE: "opaque-session"},
    ) as client:
        assert (await client.post("/api/jobs", json=request)).status_code == 403
        assert (
            await client.post(
                "/api/jobs",
                json=request,
                headers={
                    "X-CSRF-Token": "session-csrf",
                    "Origin": "https://attacker.example",
                },
            )
        ).status_code == 403
        permitted = await client.post(
            "/api/jobs",
            json=request,
            headers={
                "X-CSRF-Token": "session-csrf",
                "Origin": "http://localhost:5173",
            },
        )
        assert permitted.status_code == 202
