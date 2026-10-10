"""OIDC login is deliberately separate from permission to read a Gmail account."""

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.auth.oauth import (
    consume_state,
    discovery,
    exact_callback,
    http_client,
    json_response,
    pkce_challenge,
    start_state,
    validate_id_token,
)
from app.auth.session import (
    BROWSER_COOKIE,
    SESSION_COOKIE,
    AuthError,
    authenticate_request,
    digest,
    require_csrf,
    session_from,
    set_cookie,
    settings_from,
)
from app.db.session import database_from_request
from app.models import AuthIdentity, AuthSession, User

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    metadata = await discovery(request)
    settings = settings_from(request)
    state, browser, row = await start_state(request, "oidc")
    response = RedirectResponse(
        metadata["authorization_endpoint"]
        + ("&" if "?" in metadata["authorization_endpoint"] else "?")
        + urlencode(
            {
                "response_type": "code",
                "client_id": settings.oidc_client_id,
                "redirect_uri": settings.oidc_redirect_uri,
                "scope": "openid profile",
                "state": state,
                "nonce": row.nonce,
                "code_challenge": pkce_challenge(row.verifier),
                "code_challenge_method": "S256",
            }
        ),
        status_code=303,
    )
    set_cookie(response, BROWSER_COOKIE, browser, settings, settings.oauth_state_seconds)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/callback")
async def callback(
    request: Request, state: str = "", code: str = "", error: str = ""
) -> RedirectResponse:
    settings = settings_from(request)
    exact_callback(request, settings.oidc_redirect_uri)
    row = await consume_state(request, "oidc", state)
    if error or not code or len(code) > 4096:
        raise AuthError("OAUTH_CONSENT_FAILED", 400)
    metadata = await discovery(request)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "code_verifier": row.verifier,
        "client_id": settings.oidc_client_id,
    }
    auth: httpx.Auth = httpx.Auth()
    methods = metadata.get("token_endpoint_auth_methods_supported", ["client_secret_basic"])
    if settings.oidc_client_secret:
        if "client_secret_basic" in methods:
            auth = httpx.BasicAuth(settings.oidc_client_id, settings.oidc_client_secret)
        elif "client_secret_post" in methods:
            data["client_secret"] = settings.oidc_client_secret
        else:
            raise AuthError("OIDC_CLIENT_AUTH_UNSUPPORTED", 503)
    try:
        tokens = await json_response(
            await http_client(request).post(metadata["token_endpoint"], data=data, auth=auth)
        )
    except httpx.HTTPError as exc:
        raise AuthError("OAUTH_PROVIDER_ERROR", 502) from exc
    if not isinstance(tokens.get("id_token"), str):
        raise AuthError("OIDC_TOKEN_INVALID")
    claims = await validate_id_token(request, tokens["id_token"], metadata, row.nonce)
    token = secrets.token_urlsafe(32)
    async with database_from_request(request).session_factory()() as session, session.begin():
        existing = await session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.issuer == settings.oidc_issuer,
                AuthIdentity.subject == claims["sub"],
            )
        )
        if existing is not None:
            user_id = existing.user_id
        else:
            user_id = uuid4()
            # Do not link accounts by an email claim, even when email_verified is present.
            session.add(
                User(id=user_id, email=f"{user_id.hex}@identity.invalid", name="SpendGraph user")
            )
            await session.flush()
            inserted = await session.scalar(
                insert(AuthIdentity)
                .values(
                    id=uuid4(),
                    user_id=user_id,
                    issuer=settings.oidc_issuer,
                    subject=claims["sub"],
                )
                .on_conflict_do_nothing(index_elements=["issuer", "subject"])
                .returning(AuthIdentity.user_id)
            )
            if inserted is None:
                old_user = user_id
                mapped_user_id = await session.scalar(
                    select(AuthIdentity.user_id).where(
                        AuthIdentity.issuer == settings.oidc_issuer,
                        AuthIdentity.subject == claims["sub"],
                    )
                )
                await session.execute(delete(User).where(User.id == old_user))
                if mapped_user_id is None:
                    raise AuthError("IDENTITY_MAPPING_FAILED", 503)
                user_id = mapped_user_id
        old_token = request.cookies.get(SESSION_COOKIE)
        if old_token:
            await session.execute(
                delete(AuthSession).where(AuthSession.token_hash == digest(old_token))
            )
        await session.execute(
            delete(AuthSession).where(AuthSession.expires_at <= datetime.now(UTC))
        )
        session.add(
            AuthSession(
                token_hash=digest(token),
                user_id=user_id,
                csrf_token=secrets.token_urlsafe(32),
                expires_at=datetime.now(UTC) + timedelta(seconds=settings.auth_session_seconds),
            )
        )
    response = RedirectResponse(settings.auth_frontend_url, status_code=303)
    set_cookie(response, SESSION_COOKIE, token, settings, settings.auth_session_seconds)
    response.delete_cookie(
        BROWSER_COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="lax"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/me")
async def me(request: Request) -> JSONResponse:
    principal = await authenticate_request(request)
    dev = settings_from(request).dev_auth_enabled and not request.cookies.get(SESSION_COOKIE)
    csrf = "" if dev else (await session_from(request)).csrf_token
    async with database_from_request(request).session_factory()() as session:
        user = await session.get(User, principal.user_id)
    return JSONResponse(
        {
            "authenticated": True,
            "mode": "development" if dev else "oidc",
            "name": user.name if user else "Local developer",
            "csrfToken": csrf,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    await require_csrf(request)
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        async with database_from_request(request).session_factory()() as session, session.begin():
            await session.execute(
                delete(AuthSession).where(AuthSession.token_hash == digest(token))
            )
    response = JSONResponse({"loggedOut": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings_from(request).auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response
