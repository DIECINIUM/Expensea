"""Authentication provider boundary."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from starlette.requests import Request

from app.auth.principal import Principal


class Authenticator(Protocol):
    """Resolve one trusted application identity from an incoming request."""

    async def authenticate(self, request: Request) -> Principal:
        """Authenticate the request or raise a provider-specific auth error."""
        ...


@dataclass(frozen=True, slots=True)
class DevelopmentAuthenticator:
    """Return one server-configured identity without trusting request input."""

    user_id: UUID

    async def authenticate(self, request: Request) -> Principal:
        """Return the fixed local identity regardless of request headers."""
        del request
        return Principal(user_id=self.user_id)
