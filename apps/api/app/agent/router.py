from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agent.contracts import QuestionRequest, QuestionResult
from app.agent.service import AgentAccessError, FinanceAgentService
from app.auth.dependencies import require_csrf
from app.auth.principal import Principal
from app.ledger.errors import LedgerNotFoundError, LedgerValidationError

RequestAuthenticator = Callable[[Request], Awaitable[Principal]]
ServiceResolver = Callable[[Request], FinanceAgentService]


class PrivateAgentRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def private_response(request: Request) -> Response:
            try:
                response = await handler(request)
            except StarletteHTTPException as error:
                error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
                raise
            response.headers["Cache-Control"] = "no-store"
            return response

        return private_response


def create_agent_router(
    service: FinanceAgentService | ServiceResolver,
    authenticate: RequestAuthenticator,
    *,
    allowed_origins: tuple[str, ...] = (),
    csrf_guard: Callable[[Request], Awaitable[None]] = require_csrf,
) -> APIRouter:
    """The composition root supplies the same trusted auth helper as other APIs."""
    router = APIRouter(prefix="/api/agent", tags=["finance-agent"], route_class=PrivateAgentRoute)

    @router.post("/questions", response_model=QuestionResult)
    async def ask(request: Request) -> QuestionResult:
        origin = request.headers.get("origin")
        same_origin = f"{request.url.scheme}://{request.url.netloc}"
        if origin is not None and origin not in (same_origin, *allowed_origins):
            raise HTTPException(status_code=403, detail="Request origin is not allowed.")
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise HTTPException(status_code=415, detail="JSON content type is required.")
        principal = await authenticate(request)
        await csrf_guard(request)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 4096:
                raise HTTPException(status_code=413, detail="Question request is too large.")
            body.extend(chunk)
        try:
            question = QuestionRequest.model_validate_json(bytes(body))
        except ValidationError:
            # Never echo untrusted question/IDs in validation errors.
            raise HTTPException(status_code=422, detail="Invalid question request.") from None

        async def authorize() -> Principal:
            return await authenticate(request)

        try:
            resolved_service = service(request) if callable(service) else service
            return await resolved_service.ask(question, principal, authorize)
        except AgentAccessError:
            raise HTTPException(
                status_code=401,
                detail="Authentication must be renewed.",
            ) from None
        except LedgerNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="Matching ledger data was not found.",
            ) from None
        except LedgerValidationError:
            raise HTTPException(status_code=422, detail="Invalid ledger query.") from None

    return router
