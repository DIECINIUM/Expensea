"""Development authentication seam tests."""

from uuid import UUID

import pytest
from starlette.requests import Request

from app.auth import Authenticator, DevelopmentAuthenticator, Principal


def _request_with_untrusted_user_id(user_id: UUID) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/graphql",
            "raw_path": b"/graphql",
            "query_string": b"",
            "headers": [(b"x-user-id", str(user_id).encode("ascii"))],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
        }
    )


def _as_authenticator(authenticator: Authenticator) -> Authenticator:
    """Exercise structural protocol compatibility during static type checking."""
    return authenticator


@pytest.mark.asyncio
async def test_development_authenticator_uses_only_its_fixed_user_id() -> None:
    configured_user_id = UUID("f9229476-878d-4312-814c-867fc758f20b")
    untrusted_user_id = UUID("ed629ce7-79b3-4156-af47-663ad8bc97e3")
    authenticator = _as_authenticator(
        DevelopmentAuthenticator(user_id=configured_user_id),
    )

    principal = await authenticator.authenticate(
        _request_with_untrusted_user_id(untrusted_user_id),
    )

    assert principal == Principal(user_id=configured_user_id)
    assert principal.user_id != untrusted_user_id
