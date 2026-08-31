"""case identity and money fields

Revision ID: fa20cee8b632
Revises: 0001
Create Date: 2026-08-31 15:43:52.817114

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa20cee8b632"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills any pre-existing rows (Phase 01's test data); the ORM
    # always supplies a real value on insert, so the default only ever matters here.
    op.add_column(
        "cases",
        sa.Column("merchant_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "cases",
        sa.Column("provider_event_id", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "cases",
        sa.Column(
            "amount_at_risk", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "cases",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
    )
    op.add_column(
        "cases",
        sa.Column("customer_ref", sa.String(length=128), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("cases", "customer_ref")
    op.drop_column("cases", "currency")
    op.drop_column("cases", "amount_at_risk")
    op.drop_column("cases", "provider_event_id")
    op.drop_column("cases", "merchant_id")
