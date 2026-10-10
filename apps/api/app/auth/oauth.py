"""Bound, expiring OAuth transactions and validated standards-based OIDC discovery."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
import jwt
from fastapi import Request
from sqlalchemy import delete

from app.auth.session import BROWSER_COOKIE, AuthError, digest, settings_from
from app.db.session import database_from_request
from app.models.auth import OAuthState


def http_client(request: Request) -> httpx.AsyncClient:
    return cast(httpx.AsyncClient, request.app.state.oauth_http_client)


async def json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (httpx.HTTPError, ValueError) as exc:
        raise AuthError("OAUTH_PROVIDER_ERROR", 502) from exc


async def start_state(request: Request, purpose: str) -> tuple[str, str, OAuthState]:
    settings = settings_from(request)
    browser = secrets.token_urlsafe(32)
    state = secrets.token_urlsafe(32)
    user_id = None
    if purpose == "gmail":
        from app.auth.session import authenticate_request

        user_id = (await authenticate_request(request)).user_id
    row = OAuthState(
        state_hash=digest(state),
        purpose=purpose,
        browser_hash=digest(browser),
        user_id=user_id,
        nonce=secrets.token_urlsafe(32),
        verifier=secrets.token_urlsafe(64),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.oauth_state_seconds),
    )
    async with database_from_request(request).session_factory()() as session, session.begin():
        # Expired secrets are removed on each new transaction, not retained indefinitely.
        await session.execute(delete(OAuthState).where(OAuthState.expires_at <= datetime.now(UTC)))
        session.add(row)
    return state, browser, row


async def consume_state(request: Request, purpose: str, state: str) -> OAuthState:
    browser = request.cookies.get(BROWSER_COOKIE, "")
    if not state or len(state) > 128 or not browser or len(browser) > 128:
        raise AuthError("OAUTH_STATE_INVALID", 400)
    owner = None
    if purpose == "gmail":
        from app.auth.session import authenticate_request

        owner = (await authenticate_request(request)).user_id
    async with database_from_request(request).session_factory()() as session, session.begin():
        statement = delete(OAuthState).where(
            OAuthState.state_hash == digest(state),
            OAuthState.purpose == purpose,
            OAuthState.browser_hash == digest(browser),
            OAuthState.expires_at > datetime.now(UTC),
        )
        if owner is not None:
            statement = statement.where(OAuthState.user_id == owner)
        found = (await session.execute(statement.returning(OAuthState))).scalar_one_or_none()
    if found is None:
        raise AuthError("OAUTH_STATE_INVALID", 400)
    return found


def pkce_challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def exact_callback(request: Request, expected: str) -> None:
    actual = str(request.url.replace(query=""))
    if actual != expected:
        raise AuthError("OAUTH_CALLBACK_INVALID", 400)


async def discovery(request: Request) -> dict[str, Any]:
    issuer = settings_from(request).oidc_issuer
    if not issuer:
        raise AuthError("OIDC_NOT_CONFIGURED", 503)
    try:
        response = await http_client(request).get(
            f"{issuer.rstrip('/')}/.well-known/openid-configuration"
        )
    except httpx.HTTPError as exc:
        raise AuthError("OAUTH_PROVIDER_ERROR", 502) from exc
    data = await json_response(response)
    if data.get("issuer") != issuer:
        raise AuthError("OIDC_ISSUER_INVALID", 502)
    if "code_challenge_methods_supported" in data:
        methods = data["code_challenge_methods_supported"]
        if not isinstance(methods, list) or "S256" not in methods:
            raise AuthError("OIDC_PKCE_REQUIRED", 503)
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        endpoint = data.get(field)
        if not isinstance(endpoint, str):
            raise AuthError("OIDC_DISCOVERY_INVALID", 502)
        parts = urlsplit(endpoint)
        if (
            not parts.hostname
            or parts.username
            or parts.password
            or parts.fragment
            or (
                parts.scheme != "https"
                and not (
                    urlsplit(issuer).scheme == "http"
                    and parts.scheme == "http"
                    and parts.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        ):
            raise AuthError("OIDC_DISCOVERY_INVALID", 502)
    return data


async def validate_id_token(
    request: Request, token: str, metadata: dict[str, Any], nonce: str
) -> dict[str, Any]:
    settings = settings_from(request)
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}:
            raise ValueError
        keys = await json_response(await http_client(request).get(metadata["jwks_uri"]))
        candidates = [
            key
            for key in keys.get("keys", [])
            if isinstance(key, dict)
            and key.get("kid") == header.get("kid")
            and key.get("use", "sig") == "sig"
            and key.get("alg", algorithm) == algorithm
        ]
        if len(candidates) != 1:
            raise ValueError
        key = jwt.PyJWK.from_dict(candidates[0], algorithm=algorithm)
        claims: dict[str, Any] = jwt.decode(
            token,
            key.key,
            algorithms=[algorithm],
            audience=settings.oidc_client_id,
            issuer=settings.oidc_issuer,
            options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]},
            leeway=30,
        )
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise ValueError
        if not isinstance(claims["nonce"], str) or not secrets.compare_digest(
            claims["nonce"], nonce
        ):
            raise ValueError
        audience = claims["aud"]
        if ((isinstance(audience, list) and len(audience) > 1) or "azp" in claims) and (
            claims.get("azp") != settings.oidc_client_id
        ):
            raise ValueError
        return claims
    except httpx.HTTPError as exc:
        raise AuthError("OAUTH_PROVIDER_ERROR", 502) from exc
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise AuthError("OIDC_TOKEN_INVALID", 401) from exc
