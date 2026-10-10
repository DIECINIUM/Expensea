"""Stable request-authentication boundary shared by REST feature routers."""

from app.auth.session import AuthError, authenticate_request, require_csrf

__all__ = ["AuthError", "authenticate_request", "require_csrf"]
