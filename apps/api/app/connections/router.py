"""Official read-only Gmail OAuth and bounded minimized ingestion."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.ai.contracts import StructuredCompletionProvider
from app.ai.errors import AIError
from app.ai.extraction import FinancialNoteExtractor
from app.ai.factory import create_structured_provider
from app.ai.proposal_service import FinancialProposalService
from app.auth.oauth import (
    consume_state,
    exact_callback,
    http_client,
    json_response,
    pkce_challenge,
    start_state,
)
from app.auth.session import (
    BROWSER_COOKIE,
    AuthError,
    authenticate_request,
    digest,
    require_csrf,
    set_cookie,
    settings_from,
)
from app.connections.crypto import TokenVault
from app.connectors.gmail import GMAIL_READONLY_SCOPE, GmailReceiptConnector
from app.core.config import AIProvider, Settings
from app.db.session import Database, database_from_request
from app.domain.enums import ConnectorType, SourceConnectionStatus
from app.ingestion.errors import ConnectorUnavailableError
from app.ingestion.service import IngestionService
from app.models import GmailCredential, OAuthState, SourceConnection

router = APIRouter(prefix="/connections/gmail", tags=["connections"])
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"


def require_configured(request: Request) -> None:
    if not settings_from(request).gmail_client_id:
        raise AuthError("GMAIL_NOT_CONFIGURED", 503)


def validate_scope(tokens: dict[str, object]) -> str:
    scope = tokens.get("scope")
    if not isinstance(scope, str) or set(scope.split()) != {GMAIL_READONLY_SCOPE}:
        raise AuthError("GMAIL_SCOPE_INVALID", 403)
    return scope


@router.get("/status")
async def status(request: Request) -> JSONResponse:
    owner = (await authenticate_request(request)).user_id
    async with database_from_request(request).session_factory()() as session:
        credential = await session.get(GmailCredential, owner)
    return JSONResponse(
        {
            "configured": bool(settings_from(request).gmail_client_id),
            "status": credential.status if credential else "disconnected",
            "lastErrorCode": credential.last_error_code if credential else None,
            "lastSyncedAt": credential.last_synced_at.isoformat()
            if credential and credential.last_synced_at
            else None,
            "scope": GMAIL_READONLY_SCOPE,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/connect")
async def connect(request: Request) -> JSONResponse:
    await authenticate_request(request)
    await require_csrf(request)
    require_configured(request)
    settings = settings_from(request)
    state, browser, row = await start_state(request, "gmail")
    url = (
        AUTHORIZE_URL
        + "?"
        + urlencode(
            {
                "client_id": settings.gmail_client_id,
                "redirect_uri": settings.gmail_redirect_uri,
                "response_type": "code",
                "scope": GMAIL_READONLY_SCOPE,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "false",
                "state": state,
                "code_challenge": pkce_challenge(row.verifier),
                "code_challenge_method": "S256",
            }
        )
    )
    response = JSONResponse({"authorizationUrl": url}, headers={"Cache-Control": "no-store"})
    set_cookie(response, BROWSER_COOKIE, browser, settings, settings.oauth_state_seconds)
    return response


@router.get("/callback")
async def callback(
    request: Request, state: str = "", code: str = "", error: str = ""
) -> RedirectResponse:
    require_configured(request)
    settings = settings_from(request)
    exact_callback(request, settings.gmail_redirect_uri)
    row = await consume_state(request, "gmail", state)
    if error or not code or len(code) > 4096:
        raise AuthError("OAUTH_CONSENT_FAILED", 400)
    try:
        tokens = await json_response(
            await http_client(request).post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.gmail_client_id,
                    "client_secret": settings.gmail_client_secret,
                    "code": code,
                    "redirect_uri": settings.gmail_redirect_uri,
                    "code_verifier": row.verifier,
                },
            )
        )
    except httpx.HTTPError as exc:
        raise AuthError("OAUTH_PROVIDER_ERROR", 502) from exc
    scope = validate_scope(tokens)
    refresh = tokens.get("refresh_token")
    if not isinstance(refresh, str) or not refresh or len(refresh) > 8192:
        raise AuthError("GMAIL_OFFLINE_GRANT_REQUIRED", 400)
    key_id, ciphertext = TokenVault(settings).encrypt(refresh)
    access = tokens.get("access_token")
    if not isinstance(access, str) or not access:
        raise AuthError("GMAIL_TOKEN_INVALID", 502)
    try:
        profile = await json_response(
            await http_client(request).get(
                "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                headers={"Authorization": f"Bearer {access}"},
            )
        )
    except httpx.HTTPError as exc:
        raise AuthError("OAUTH_PROVIDER_ERROR", 502) from exc
    account = profile.get("emailAddress")
    if not isinstance(account, str) or not account or len(account) > 254:
        raise AuthError("GMAIL_ACCOUNT_INVALID", 502)
    account_key = digest(account.strip().lower())
    async with database_from_request(request).session_factory()() as session, session.begin():
        persisted_owner = await session.scalar(
            insert(GmailCredential)
            .values(
                user_id=row.user_id,
                refresh_ciphertext=ciphertext,
                key_id=key_id,
                scopes=scope,
                account_key=account_key,
                status="connected",
            )
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={
                    "refresh_ciphertext": ciphertext,
                    "key_id": key_id,
                    "scopes": scope,
                    "status": "connected",
                    "last_error_code": None,
                    "account_key": account_key,
                    "disconnected_at": None,
                },
                where=(
                    GmailCredential.disconnected_at.is_(None)
                    | (GmailCredential.disconnected_at < row.created_at)
                ),
            )
            .returning(GmailCredential.user_id)
        )
        if persisted_owner is None:
            raise AuthError("GMAIL_CONNECTION_CANCELLED", 409)
        await session.execute(
            update(SourceConnection)
            .where(
                SourceConnection.user_id == row.user_id,
                SourceConnection.connector_type == ConnectorType.GMAIL,
            )
            .values(status=SourceConnectionStatus.DISCONNECTED)
        )
        await session.execute(
            update(SourceConnection)
            .where(
                SourceConnection.user_id == row.user_id,
                SourceConnection.connector_type == ConnectorType.GMAIL,
                SourceConnection.connection_key == account_key,
            )
            .values(status=SourceConnectionStatus.ACTIVE)
        )
    response = RedirectResponse(settings.auth_frontend_url, status_code=303)
    response.delete_cookie(
        BROWSER_COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="lax"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


async def refresh_access(
    settings: Settings, client: httpx.AsyncClient, credential: GmailCredential
) -> str:
    if credential.status in {"revoked", "disconnected"} or not credential.refresh_ciphertext:
        raise AuthError("GMAIL_RECONNECT_REQUIRED", 409)
    if set(credential.scopes.split()) != {GMAIL_READONLY_SCOPE}:
        raise AuthError("GMAIL_SCOPE_INVALID", 403)
    vault = TokenVault(settings)
    refresh_token = vault.decrypt(credential.key_id, credential.refresh_ciphertext)
    try:
        response = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.gmail_client_id,
                "client_secret": settings.gmail_client_secret,
            },
        )
        if response.status_code == 400:
            error = response.json().get("error")
            if error == "invalid_grant":
                credential.status = "revoked"
                credential.refresh_ciphertext = None
                credential.last_error_code = "GMAIL_GRANT_REVOKED"
                raise AuthError("GMAIL_GRANT_REVOKED", 409)
        tokens = await json_response(response)
        if "scope" in tokens:
            credential.scopes = validate_scope(tokens)
        access = tokens.get("access_token")
        if (
            not isinstance(access, str)
            or not access
            or (str(tokens.get("token_type", "")).lower() != "bearer")
        ):
            raise AuthError("GMAIL_TOKEN_INVALID", 502)
        rotated = tokens.get("refresh_token", refresh_token)
        if not isinstance(rotated, str) or not rotated:
            raise AuthError("GMAIL_TOKEN_INVALID", 502)
        credential.key_id, credential.refresh_ciphertext = vault.encrypt(rotated)
        credential.status = "connected"
        credential.last_error_code = None
        return access
    except (httpx.HTTPError, ValueError) as exc:
        raise AuthError("OAUTH_PROVIDER_ERROR", 502) from exc


async def operate(request: Request, *, sync: bool) -> JSONResponse:
    owner = (await authenticate_request(request)).user_id
    await require_csrf(request)
    require_configured(request)
    result = await run_gmail(
        database_from_request(request),
        settings_from(request),
        http_client(request),
        owner,
        sync=sync,
        structured_provider=cast(
            StructuredCompletionProvider, request.app.state.structured_provider
        ),
    )
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


async def run_gmail(
    database: Database,
    settings: Settings,
    client: httpx.AsyncClient,
    owner: UUID,
    *,
    sync: bool,
    structured_provider: StructuredCompletionProvider | None = None,
) -> dict[str, object]:
    """Bound the complete operation below the edge timeout; ingestion remains replay-safe."""
    try:
        async with asyncio.timeout(settings.gmail_operation_timeout_seconds):
            return await _run_gmail(
                database,
                settings,
                client,
                owner,
                sync=sync,
                structured_provider=structured_provider,
            )
    except TimeoutError as exc:
        try:
            async with asyncio.timeout(5):
                async with database.session_factory()() as session, session.begin():
                    await session.execute(
                        update(GmailCredential)
                        .where(
                            GmailCredential.user_id == owner,
                            GmailCredential.status.in_(["connected", "error"]),
                        )
                        .values(status="error", last_error_code="GMAIL_OPERATION_TIMEOUT")
                    )
        except (TimeoutError, SQLAlchemyError):
            # Database unavailability must not defeat the bounded HTTP response.
            pass
        raise AuthError("GMAIL_OPERATION_TIMEOUT", 504) from exc


async def _run_gmail(
    database: Database,
    settings: Settings,
    client: httpx.AsyncClient,
    owner: UUID,
    *,
    sync: bool,
    structured_provider: StructuredCompletionProvider | None = None,
) -> dict[str, object]:
    """Worker-safe operation: owner is trusted queue metadata, never browser-supplied."""
    if not settings.gmail_client_id:
        raise AuthError("GMAIL_NOT_CONFIGURED", 503)
    failure = None
    result = None
    proposals = 0
    extraction_errors: list[str] = []
    async with database.session_factory()() as session, session.begin():
        credential = await session.scalar(
            select(GmailCredential).where(GmailCredential.user_id == owner).with_for_update()
        )
        if credential is None:
            raise AuthError("GMAIL_NOT_CONNECTED", 409)
        try:
            access = await refresh_access(settings, client, credential)
            if sync:
                connector = GmailReceiptConnector(
                    access_token=access,
                    client=client,
                    max_results=settings.gmail_sync_max_results,
                )
                result = await IngestionService(database).sync_connector(
                    owner, connector, connection_key=credential.account_key
                )
                credential.last_synced_at = datetime.now(UTC)
                if settings.ai_provider is not AIProvider.DISABLED:
                    proposal_service = FinancialProposalService(
                        database,
                        FinancialNoteExtractor(
                            structured_provider or create_structured_provider(settings),
                            max_input_chars=settings.ai_max_input_chars,
                            review_confidence_threshold=Decimal(
                                str(settings.ai_review_confidence_threshold)
                            ),
                        ),
                    )
                    for event in result.events:
                        try:
                            await proposal_service.extract_raw_event(owner, event.raw_event_id)
                            proposals += 1
                        except AIError as exc:
                            extraction_errors.append(exc.code)
        except AuthError as exc:
            failure = exc
            credential.last_error_code = exc.code
            if credential.status not in {"revoked", "disconnected"}:
                credential.status = "error"
        except ConnectorUnavailableError as exc:
            credential.last_error_code = exc.code
            credential.status = "error"
            failure = AuthError(exc.code, 502)
    if failure:
        raise failure
    return {
        "refreshed": True,
        "synced": sync,
        "events": len(result.events) if result else 0,
        "proposals": proposals,
        "extractionStatus": "disabled"
        if settings.ai_provider is AIProvider.DISABLED
        else "errors"
        if extraction_errors
        else "completed",
        "extractionErrorCodes": extraction_errors,
        "needsReview": sum(event.state.value == "needs_review" for event in result.events)
        if result
        else 0,
    }


async def sync_gmail(
    database: Database, settings: Settings, client: httpx.AsyncClient, user_id: UUID
) -> dict[str, object]:
    return await run_gmail(database, settings, client, user_id, sync=True)


@router.post("/sync")
async def sync(request: Request) -> JSONResponse:
    return await operate(request, sync=True)


@router.post("/refresh")
async def refresh(request: Request) -> JSONResponse:
    return await operate(request, sync=False)


@router.post("/disconnect")
async def disconnect(request: Request) -> JSONResponse:
    owner = (await authenticate_request(request)).user_id
    await require_csrf(request)
    revoked = False
    async with database_from_request(request).session_factory()() as session, session.begin():
        credential = await session.scalar(
            select(GmailCredential).where(GmailCredential.user_id == owner).with_for_update()
        )
        if credential and credential.refresh_ciphertext:
            try:
                token = TokenVault(settings_from(request)).decrypt(
                    credential.key_id, credential.refresh_ciphertext
                )
                response = await http_client(request).post(REVOKE_URL, data={"token": token})
                revoked = response.status_code == 200
            except (httpx.HTTPError, AuthError):
                revoked = False
        # A non-secret tombstone also defeats callbacks already exchanging a code
        # when disconnect happens. Clearing only pending state would leave that race.
        await session.execute(
            insert(GmailCredential)
            .values(
                user_id=owner,
                refresh_ciphertext=None,
                key_id="",
                scopes="",
                account_key="",
                status="disconnected",
                disconnected_at=func.clock_timestamp(),
            )
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={
                    "refresh_ciphertext": None,
                    "key_id": "",
                    "scopes": "",
                    "account_key": "",
                    "status": "disconnected",
                    "disconnected_at": func.clock_timestamp(),
                    "last_error_code": None,
                    "last_synced_at": None,
                },
            )
        )
        await session.execute(
            delete(OAuthState).where(
                OAuthState.user_id == owner,
                OAuthState.purpose == "gmail",
            )
        )
        await session.execute(
            update(SourceConnection)
            .where(
                SourceConnection.user_id == owner,
                SourceConnection.connector_type == ConnectorType.GMAIL,
            )
            .values(status=SourceConnectionStatus.DISCONNECTED)
        )
    return JSONResponse(
        {"disconnected": True, "providerRevoked": revoked},
        headers={"Cache-Control": "no-store"},
    )
