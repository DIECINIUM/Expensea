"""Synthetic-provider checks for cookie identity and isolated read-only grants."""

import asyncio
import base64
import importlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import jwt
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import func, select, update
from starlette.requests import Request

from app.ai.mock import MockStructuredProvider
from app.auth.oauth import pkce_challenge, validate_id_token
from app.auth.session import SESSION_COOKIE, AuthError, OAuthAccessLogFilter, digest
from app.connections.crypto import TokenVault
from app.connectors.gmail import GMAIL_READONLY_SCOPE
from app.core.config import AIProvider, Settings
from app.db.session import Database
from app.factory import create_app
from app.models import (
    AuthIdentity,
    AuthSession,
    FinancialEventProposal,
    GmailCredential,
    LedgerTransaction,
    OAuthState,
    RawEvent,
)

ISSUER = "https://identity.example.test"
REDIRECT = "http://localhost:8000/auth/callback"


class SyntheticProvider:
    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.nonce = ""
        self.subject = "owner-one"
        self.scope = GMAIL_READONLY_SCOPE
        self.revoked = False
        self.messages = 0
        self.fail_revoke = False
        self.calls: list[httpx.Request] = []

    def id_token(self, **overrides: Any) -> str:
        now = datetime.now(UTC)
        claims = {
            "iss": ISSUER,
            "sub": self.subject,
            "aud": "client",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "nonce": self.nonce,
        }
        claims.update(overrides)
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "key-one"})

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/keys",
                },
            )
        if request.url.path == "/keys":
            key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
            return httpx.Response(200, json={"keys": [{**key, "kid": "key-one", "alg": "RS256"}]})
        if request.url.host == "identity.example.test" and request.url.path == "/token":
            return httpx.Response(200, json={"id_token": self.id_token()})
        if request.url.host == "oauth2.googleapis.com":
            if request.url.path == "/revoke":
                return httpx.Response(503 if self.fail_revoke else 200)
            fields = parse_qs(request.content.decode())
            if fields.get("grant_type") == ["refresh_token"] and self.revoked:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200,
                json={
                    "access_token": "synthetic-access",
                    "token_type": "Bearer",
                    "refresh_token": "synthetic-refresh",
                    "scope": self.scope,
                },
            )
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "synthetic@example.test"})
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200, json={"messages": [{"id": f"msg-{index}"} for index in range(self.messages)]}
            )
        if "/messages/msg-" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "id": request.url.path.rsplit("/", 1)[-1],
                    "snippet": "Receipt: INR 120 paid",
                    "internalDate": "1784000000000",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "Subject", "value": "Synthetic receipt"},
                            {"name": "From", "value": "Shop <private-synthetic@example.test>"},
                        ],
                        "body": {
                            "data": base64.urlsafe_b64encode(
                                ("Receipt INR 120 " + "x" * 8000 + "discarded-footer").encode()
                            ).decode()
                        },
                    },
                },
            )
        return httpx.Response(500, json={"error": "unexpected_mock_request"})


def auth_settings(**overrides: Any) -> Settings:
    fields: dict[str, Any] = {
        "_env_file": None,
        "app_env": "test",
        "dev_auth_enabled": False,
        "oidc_issuer": ISSUER,
        "oidc_client_id": "client",
        "oidc_redirect_uri": REDIRECT,
        "auth_frontend_url": "http://localhost:5173",
        "cors_origins": '["http://localhost:5173"]',
        "gmail_client_id": "gmail-client",
        "gmail_client_secret": "synthetic-secret",
        "gmail_sync_max_results": 1,
        "token_encryption_active_key_id": "local-key",
        "token_encryption_keys": json.dumps({"local-key": Fernet.generate_key().decode()}),
    }
    fields.update(overrides)
    return Settings(**fields)


@pytest.fixture
async def auth_app(isolated_database: Database) -> Any:
    app = create_app(auth_settings())
    app.state.database = isolated_database
    provider = SyntheticProvider()
    original = app.state.oauth_http_client
    await original.aclose()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handle)) as client:
        app.state.oauth_http_client = client
        yield app, provider


async def sign_in(client: httpx.AsyncClient, provider: SyntheticProvider) -> str:
    login = await client.get("/auth/login")
    assert login.status_code == 303
    query = parse_qs(urlsplit(login.headers["location"]).query)
    provider.nonce = query["nonce"][0]
    assert query["scope"] == ["openid profile"]
    assert query["code_challenge_method"] == ["S256"]
    response = await client.get(
        "/auth/callback",
        params={
            "state": query["state"][0],
            "code": "synthetic-code",
        },
    )
    assert response.status_code == 303, response.text
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    return query["state"][0]


async def mutation_headers(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.get("/auth/me")
    assert response.status_code == 200
    return {"Origin": "http://localhost:5173", "X-CSRF-Token": response.json()["csrfToken"]}


@pytest.mark.database
async def test_oidc_owner_cookie_rotation_replay_csrf_and_logout(auth_app: Any) -> None:
    app, provider = auth_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
    ) as client:
        assert (
            await client.get("/auth/me", headers={"X-User-ID": str(uuid4())})
        ).status_code == 401
        state = await sign_in(client, provider)
        token = client.cookies[SESSION_COOKIE]
        headers = await mutation_headers(client)
        assert (await client.post("/auth/logout")).status_code == 403
        assert (
            await client.post(
                "/auth/logout",
                headers={
                    **headers,
                    "Origin": "https://attacker.example",
                },
            )
        ).status_code == 403
        assert (
            await client.get(
                "/auth/callback",
                params={
                    "state": state,
                    "code": "replayed",
                },
            )
        ).status_code == 400
        async with app.state.database.session_factory()() as session:
            persisted = await session.get(AuthSession, digest(token))
            assert persisted is not None and persisted.token_hash != token
            user_id = persisted.user_id
        await sign_in(client, provider)
        assert client.cookies[SESSION_COOKIE] != token
        async with app.state.database.session_factory()() as session:
            assert await session.get(AuthSession, digest(token)) is None
            assert await session.scalar(select(func.count()).select_from(AuthIdentity)) == 1
            assert await session.scalar(select(AuthSession.user_id)) == user_id
        headers = await mutation_headers(client)
        mutation = "mutation { createTransaction(input: {}) { id } }"
        assert (await client.post("/graphql", json={"query": mutation})).status_code == 403
        assert (await client.post("/auth/logout", headers=headers)).status_code == 200
        client.cookies.set(SESSION_COOKIE, token)
        assert (await client.get("/auth/me")).status_code == 401


@pytest.mark.database
async def test_state_browser_expiry_and_exact_callback(auth_app: Any) -> None:
    app, provider = auth_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
    ) as client:
        login = await client.get("/auth/login")
        query = parse_qs(urlsplit(login.headers["location"]).query)
        provider.nonce = query["nonce"][0]
        params = {"state": query["state"][0], "code": "synthetic"}
        wrong_origin = await client.get("http://127.0.0.1:8000/auth/callback", params=params)
        assert wrong_origin.status_code == 400
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
        ) as other:
            assert (await other.get("/auth/callback", params=params)).status_code == 400
        async with app.state.database.session_factory()() as session, session.begin():
            await session.execute(
                update(OAuthState).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        assert (await client.get("/auth/callback", params=params)).status_code == 400


@pytest.mark.parametrize(
    "claim,value",
    [
        ("iss", "https://attacker.test"),
        ("aud", "other-client"),
        ("nonce", "replayed"),
        ("exp", 1),
        ("sub", ""),
        ("azp", "other-client"),
    ],
)
async def test_oidc_claim_validation_rejects_invalid_tokens(claim: str, value: Any) -> None:
    provider = SyntheticProvider()
    provider.nonce = "nonce"
    app = create_app(auth_settings())
    await app.state.oauth_http_client.aclose()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handle)) as client:
        app.state.oauth_http_client = client
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
                "app": app,
            }
        )
        with pytest.raises(AuthError, match="401"):
            await validate_id_token(
                request,
                provider.id_token(**{claim: value}),
                {"jwks_uri": f"{ISSUER}/keys"},
                "nonce",
            )


async def test_oidc_rejects_unsigned_hmac_and_wrong_signature() -> None:
    provider = SyntheticProvider()
    provider.nonce = "nonce"
    app = create_app(auth_settings())
    await app.state.oauth_http_client.aclose()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handle)) as client:
        app.state.oauth_http_client = client
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": app})
        rogue = SyntheticProvider()
        rogue.nonce = "nonce"
        tokens = [
            jwt.encode({"sub": "attacker"}, key="", algorithm="none"),
            jwt.encode({"sub": "attacker"}, key="synthetic-secret" * 4, algorithm="HS256"),
            rogue.id_token(),
        ]
        for token in tokens:
            with pytest.raises(AuthError):
                await validate_id_token(request, token, {"jwks_uri": f"{ISSUER}/keys"}, "nonce")


def test_token_vault_rotation_and_tamper_fail_closed() -> None:
    old = Fernet.generate_key().decode()
    new = Fernet.generate_key().decode()
    settings = auth_settings(
        token_encryption_keys=json.dumps({"old": old}), token_encryption_active_key_id="old"
    )
    key, encrypted = TokenVault(settings).encrypt("synthetic-refresh")
    assert "synthetic-refresh" not in encrypted
    rotated = auth_settings(
        token_encryption_keys=json.dumps({"old": old, "new": new}),
        token_encryption_active_key_id="new",
    )
    vault = TokenVault(rotated)
    assert vault.decrypt(key, encrypted) == "synthetic-refresh"
    assert vault.encrypt(vault.decrypt(key, encrypted))[0] == "new"
    with pytest.raises(AuthError):
        vault.decrypt("missing-key", encrypted)
    with pytest.raises(AuthError):
        vault.decrypt(key, encrypted[:-5] + "wrong")
    assert len(pkce_challenge(secrets.token_urlsafe(64))) == 43


@pytest.mark.database
async def test_gmail_connect_scope_owner_isolation_sync_refresh_revocation(auth_app: Any) -> None:
    app, provider = auth_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
    ) as owner:
        await sign_in(owner, provider)
        headers = await mutation_headers(owner)
        assert (await owner.post("/connections/gmail/connect")).status_code == 403
        started = await owner.post("/connections/gmail/connect", headers=headers)
        assert started.status_code == 200
        query = parse_qs(urlsplit(started.json()["authorizationUrl"]).query)
        assert query["scope"] == [GMAIL_READONLY_SCOPE]
        assert query["code_challenge_method"] == ["S256"]
        provider.subject = "owner-two"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
        ) as other:
            await sign_in(other, provider)
            other.cookies.set("spendgraph_oauth_browser", owner.cookies["spendgraph_oauth_browser"])
            params = {"state": query["state"][0], "code": "synthetic"}
            assert (
                await other.get("/connections/gmail/callback", params=params)
            ).status_code == 400
            assert (
                await owner.get("/connections/gmail/callback", params=params)
            ).status_code == 303
            assert (
                await owner.get("/connections/gmail/callback", params=params)
            ).status_code == 400
            assert (await other.get("/connections/gmail/status")).json()["status"] == "disconnected"
        async with app.state.database.session_factory()() as session:
            credential = await session.scalar(select(GmailCredential))
            assert credential and "synthetic-refresh" not in credential.refresh_ciphertext
        provider.messages = 3
        synced = await owner.post("/connections/gmail/sync", headers=headers)
        assert synced.status_code == 200, synced.text
        assert synced.json()["events"] == 1
        assert synced.json()["needsReview"] == 1
        assert synced.json()["extractionStatus"] == "disabled"
        async with app.state.database.session_factory()() as session:
            raw = await session.scalar(select(RawEvent))
            assert raw and len(raw.payload["extraction_text"]) <= 6000
            assert "private-synthetic" not in json.dumps(raw.payload)
            assert "discarded-footer" not in json.dumps(raw.payload)
            assert await session.scalar(select(func.count()).select_from(LedgerTransaction)) == 0
            assert (
                await session.scalar(select(func.count()).select_from(FinancialEventProposal)) == 0
            )
        assert (await owner.post("/connections/gmail/refresh", headers=headers)).status_code == 200
        provider.revoked = True
        revoked = await owner.post("/connections/gmail/refresh", headers=headers)
        assert revoked.status_code == 409
        assert (await owner.get("/connections/gmail/status")).json()["status"] == "revoked"
        async with app.state.database.session_factory()() as session:
            credential = await session.scalar(select(GmailCredential))
            assert credential and credential.refresh_ciphertext is None
        assert (await owner.post("/connections/gmail/sync", headers=headers)).status_code == 409
        result = await owner.post("/connections/gmail/disconnect", headers=headers)
        assert result.status_code == 200 and result.json()["disconnected"]
        assert (await owner.get("/connections/gmail/status")).json()["status"] == "disconnected"


@pytest.mark.database
@pytest.mark.parametrize("fail_revoke", [False, True])
async def test_gmail_scope_failure_and_remote_disconnect_truth(
    auth_app: Any,
    fail_revoke: bool,
) -> None:
    app, provider = auth_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
    ) as client:
        await sign_in(client, provider)
        headers = await mutation_headers(client)
        response = await client.post("/connections/gmail/connect", headers=headers)
        query = parse_qs(urlsplit(response.json()["authorizationUrl"]).query)
        provider.scope = "https://mail.google.com/"
        response = await client.get(
            "/connections/gmail/callback",
            params={
                "state": query["state"][0],
                "code": "synthetic",
            },
        )
        assert response.status_code == 403
        async with app.state.database.session_factory()() as session:
            assert await session.scalar(select(func.count()).select_from(GmailCredential)) == 0
        provider.scope = GMAIL_READONLY_SCOPE
        response = await client.post("/connections/gmail/connect", headers=headers)
        query = parse_qs(urlsplit(response.json()["authorizationUrl"]).query)
        assert (
            await client.get(
                "/connections/gmail/callback",
                params={
                    "state": query["state"][0],
                    "code": "synthetic",
                },
            )
        ).status_code == 303
        provider.fail_revoke = fail_revoke
        result = await client.post("/connections/gmail/disconnect", headers=headers)
        assert result.json() == {"disconnected": True, "providerRevoked": not fail_revoke}
        assert any(request.url.path == "/revoke" for request in provider.calls)
        assert (await client.post("/connections/gmail/sync", headers=headers)).status_code == 409


@pytest.mark.database
async def test_expired_cookie_cannot_select_browser_owner(auth_app: Any) -> None:
    app, provider = auth_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
    ) as client:
        await sign_in(client, provider)
        async with app.state.database.session_factory()() as session, session.begin():
            await session.execute(
                update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        assert (
            await client.get("/auth/me", headers={"X-User-ID": str(uuid4())})
        ).status_code == 401
        assert (await client.get("/connections/gmail/status")).status_code == 401


@pytest.mark.database
async def test_auth_migration_round_trip(isolated_database: Database) -> None:
    module = importlib.import_module("migrations.versions.20261011_0008_auth_connections")
    assert module.down_revision == "20260727_0007"

    def round_trip(connection: Any) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
            module.upgrade()
        import sqlalchemy as sa

        inspector = sa.inspect(connection)
        assert {"account_key", "key_id", "refresh_ciphertext"} <= {
            column["name"] for column in inspector.get_columns("gmail_credentials")
        }
        assert inspector.get_unique_constraints("auth_identities")[0]["column_names"] == [
            "issuer",
            "subject",
        ]

    async with isolated_database.engine().begin() as connection:
        await connection.run_sync(round_trip)


@pytest.mark.database
@pytest.mark.parametrize("extract_success", [True, False])
async def test_gmail_review_proposal_and_extraction_failure_are_explicit(
    auth_app: Any,
    extract_success: bool,
) -> None:
    app, provider = auth_app
    app.state.settings = app.state.settings.model_copy(update={"ai_provider": AIProvider.OLLAMA})
    mock_ai = MockStructuredProvider(
        [
            {
                "event_kind": "expense",
                "amount": "120.00",
                "currency": "INR",
                "description": "Synthetic receipt",
                "confidence": "0.90",
            }
        ]
        if extract_success
        else []
    )
    app.state.structured_provider = mock_ai
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
    ) as client:
        await sign_in(client, provider)
        headers = await mutation_headers(client)
        connected = await client.post("/connections/gmail/connect", headers=headers)
        query = parse_qs(urlsplit(connected.json()["authorizationUrl"]).query)
        assert (
            await client.get(
                "/connections/gmail/callback",
                params={
                    "state": query["state"][0],
                    "code": "synthetic",
                },
            )
        ).status_code == 303
        provider.messages = 1
        response = await client.post("/connections/gmail/sync", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["extractionStatus"] == ("completed" if extract_success else "errors")
        assert response.json()["proposals"] == int(extract_success)
        assert response.json()["extractionErrorCodes"] == (
            [] if extract_success else ["MOCK_PROVIDER_EXHAUSTED"]
        )
        async with app.state.database.session_factory()() as session:
            assert await session.scalar(select(func.count()).select_from(LedgerTransaction)) == 0
            proposal = await session.scalar(select(FinancialEventProposal))
            if extract_success:
                assert proposal and proposal.status.value == "needs_review"
            else:
                assert proposal is None
        if extract_success:
            replay = await client.post("/connections/gmail/sync", headers=headers)
            assert replay.status_code == 200
            assert len(mock_ai.requests) == 1


def test_callback_access_log_redacts_code_and_state() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "test",
        1,
        "%s - %s %s HTTP/%s %s",
        ("127.0.0.1", "GET", "/auth/callback?code=secret&state=state", "1.1", 303),
        None,
    )
    assert OAuthAccessLogFilter().filter(record)
    assert "secret" not in record.getMessage()
    assert "/auth/callback" in record.getMessage()


@pytest.mark.database
async def test_disconnect_cancels_pending_and_already_exchanging_callback(auth_app: Any) -> None:
    app, provider = auth_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
    ) as client:
        await sign_in(client, provider)
        headers = await mutation_headers(client)
        connected = await client.post("/connections/gmail/connect", headers=headers)
        query = parse_qs(urlsplit(connected.json()["authorizationUrl"]).query)
        exchanging = asyncio.Event()
        release = asyncio.Event()

        async def delayed(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com" and request.url.path == "/token":
                exchanging.set()
                await release.wait()
            return cast(SyntheticProvider, provider).handle(request)

        original = app.state.oauth_http_client
        async with httpx.AsyncClient(transport=httpx.MockTransport(delayed)) as mocked:
            app.state.oauth_http_client = mocked
            task = asyncio.create_task(
                client.get(
                    "/connections/gmail/callback",
                    params={
                        "state": query["state"][0],
                        "code": "synthetic",
                    },
                )
            )
            try:
                await asyncio.wait_for(exchanging.wait(), timeout=5)
                assert (
                    await client.post("/connections/gmail/disconnect", headers=headers)
                ).status_code == 200
            finally:
                release.set()
            response = await task
            assert response.status_code == 409
        app.state.oauth_http_client = original
        assert (await client.get("/connections/gmail/status")).json()["status"] == "disconnected"
        async with app.state.database.session_factory()() as session:
            row = await session.scalar(select(GmailCredential))
            assert row and row.refresh_ciphertext is None and not row.account_key
        # A new, deliberate consent after disconnect is still allowed.
        connected = await client.post("/connections/gmail/connect", headers=headers)
        query = parse_qs(urlsplit(connected.json()["authorizationUrl"]).query)
        assert (
            await client.get(
                "/connections/gmail/callback",
                params={
                    "state": query["state"][0],
                    "code": "new-consent",
                },
            )
        ).status_code == 303


@pytest.mark.database
async def test_gmail_total_budget_timeout_persists_retryable_state(auth_app: Any) -> None:
    app, provider = auth_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
    ) as client:
        await sign_in(client, provider)
        headers = await mutation_headers(client)
        connected = await client.post("/connections/gmail/connect", headers=headers)
        query = parse_qs(urlsplit(connected.json()["authorizationUrl"]).query)
        assert (
            await client.get(
                "/connections/gmail/callback",
                params={
                    "state": query["state"][0],
                    "code": "synthetic",
                },
            )
        ).status_code == 303
        app.state.settings = app.state.settings.model_copy(
            update={
                "gmail_operation_timeout_seconds": 0.01,
            }
        )
        original = app.state.oauth_http_client

        async def delayed(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(1)
            return cast(SyntheticProvider, provider).handle(request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(delayed)) as mocked:
            app.state.oauth_http_client = mocked
            response = await client.post("/connections/gmail/sync", headers=headers)
            assert response.status_code == 504
            assert response.json()["detail"]["code"] == "GMAIL_OPERATION_TIMEOUT"
        app.state.oauth_http_client = original
        connection = await client.get("/connections/gmail/status")
        assert connection.json()["status"] == "error"
        assert connection.json()["lastErrorCode"] == "GMAIL_OPERATION_TIMEOUT"
        async with app.state.database.session_factory()() as session:
            grant = await session.scalar(select(GmailCredential))
            assert grant and grant.refresh_ciphertext
            assert await session.scalar(select(func.count()).select_from(LedgerTransaction)) == 0
        app.state.settings = app.state.settings.model_copy(
            update={
                "gmail_operation_timeout_seconds": 120,
            }
        )
        # Retry recovers using the retained grant; no additional consent is required.
        response = await client.post("/connections/gmail/sync", headers=headers)
        assert response.status_code == 200, response.text
        assert (await client.get("/connections/gmail/status")).json()["status"] == "connected"
