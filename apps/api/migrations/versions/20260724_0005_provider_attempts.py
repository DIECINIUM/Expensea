"""Record bounded AI provider attempt counts.

Revision ID: 20260724_0005
Revises: 20260724_0004
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0005"
down_revision: str | None = "20260724_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add content-free retry observability to successful proposals."""
    op.add_column(
        "financial_event_proposals",
        sa.Column(
            "provider_attempt_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_financial_event_proposals_provider_attempt_count_range"),
        "financial_event_proposals",
        "provider_attempt_count >= 1 AND provider_attempt_count <= 4",
    )


def downgrade() -> None:
    """Remove provider attempt metadata without changing proposal content."""
    op.drop_constraint(
        op.f("ck_financial_event_proposals_provider_attempt_count_range"),
        "financial_event_proposals",
        type_="check",
    )
    op.drop_column("financial_event_proposals", "provider_attempt_count")
