"""link_redemptions and customer_opt_outs tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "link_redemptions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=26), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_link_redemptions_case_id", "link_redemptions", ["case_id"])

    op.create_table(
        "customer_opt_outs",
        sa.Column("customer_ref", sa.String(length=128), nullable=False),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_case_id", sa.String(length=26), nullable=False),
        sa.PrimaryKeyConstraint("customer_ref"),
    )
    op.create_index("ix_customer_opt_outs_merchant_id", "customer_opt_outs", ["merchant_id"])


def downgrade() -> None:
    op.drop_index("ix_customer_opt_outs_merchant_id", table_name="customer_opt_outs")
    op.drop_table("customer_opt_outs")
    op.drop_index("ix_link_redemptions_case_id", table_name="link_redemptions")
    op.drop_table("link_redemptions")
