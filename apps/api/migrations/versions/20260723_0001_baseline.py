"""Establish the empty Phase 0 schema baseline.

Revision ID: 20260723_0001
Revises:
Create Date: 2026-07-23
"""

revision: str = "20260723_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Establish the version boundary; finance tables begin in Phase 1."""


def downgrade() -> None:
    """Remove the empty baseline revision."""
