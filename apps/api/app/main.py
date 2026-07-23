"""Uvicorn entry point.

Import the pure application factory from ``app.factory`` in tests and tooling so
ambient environment settings are not read during test collection.
"""

from app.factory import create_app

app = create_app()
