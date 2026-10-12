"""Reusable REST authentication and CSRF checks; browser input never selects an owner."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime
from typing import cast

from fastapi import HTTPException, Request, Response
from sqlalchemy import select

from app.auth.principal import Principal
from app.core.config import Settings
from app.db.session import database_from_request
from app.models.auth import AuthSession

SESSION_COOKIE = "spendgraph_session"
BROWSER_COOKIE = "spendgraph_oauth_browser"


class OAuthAccessLogFilter(logging.Filter):
    """Prevent Uvicorn's access logger from retaining callback codes and state."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            path = record.args[2]
            if isinstance(path, str) and path.split("?", 1)[0] in {
                "/auth/callback",
                "/connections/gmail/callback",
            }:
                record.args = (*record.args[:2], path.split("?", 1)[0], *record.args[3:])
        return True


class AuthError(HTTPException):
    def __init__(self, code: str = "AUTH_REQUIRED", status_code: int = 401) -> None:
        self.code = code
        super().__init__(status_code=status_code, detail={"code": code})


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def settings_from(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


async def session_from(request: Request) -> AuthSession:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token or len(token) > 128:
        raise AuthError()
    async with database_from_request(request).session_factory()() as session:
        found = await session.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == digest(token), AuthSession.expires_at > datetime.now(UTC)
            )
        )
    if found is None:
        raise AuthError()
    return found


async def authenticate_request(request: Request) -> Principal:
    """Resolve an opaque persisted cookie, or the explicitly enabled local dev identity."""
    if request.cookies.get(SESSION_COOKIE):
        return Principal(user_id=(await session_from(request)).user_id)
    settings = settings_from(request)
    if settings.dev_auth_enabled:
        return Principal(user_id=settings.dev_user_id)
    raise AuthError()


async def require_csrf(request: Request) -> None:
    """Require exact trusted browser Origin and session-bound token on cookie writes."""
    if settings_from(request).dev_auth_enabled and not request.cookies.get(SESSION_COOKIE):
        return
    session = await session_from(request)
    token = request.headers.get("X-CSRF-Token", "")
    if request.headers.get("Origin") not in settings_from(request).cors_origin_list or (
        not token or not secrets.compare_digest(token, session.csrf_token)
    ):
        raise AuthError("CSRF_INVALID", 403)


def set_cookie(response: Response, name: str, value: str, settings: Settings, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
