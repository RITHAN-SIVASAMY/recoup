"""staged_actions and pending_approvals tables

Revision ID: 0005
Revises: 0a32fa92ab95
Create Date: 2026-09-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0a32fa92ab95"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staged_actions",
        sa.Column("staged_action_id", sa.String(length=26), nullable=False),
        sa.Column("case_id", sa.String(length=26), nullable=False),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=True),
        sa.Column("ladder_step", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("estimated_cost_inr", sa.Numeric(14, 2), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("staged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promote_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="staged"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("staged_action_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_staged_actions_idempotency_key"),
    )
    op.create_index("ix_staged_actions_case_id", "staged_actions", ["case_id"])
    op.create_index("ix_staged_actions_merchant_id", "staged_actions", ["merchant_id"])

    op.create_table(
        "pending_approvals",
        sa.Column("approval_id", sa.String(length=26), nullable=False),
        sa.Column("case_id", sa.String(length=26), nullable=False),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=True),
        sa.Column("ladder_step", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_inr", sa.Numeric(14, 2), nullable=False),
        sa.Column("expected_value_inr", sa.Numeric(14, 2), nullable=False),
        sa.Column("uplift", sa.Numeric(6, 4), nullable=False),
        sa.Column("root_cause", sa.String(length=64), nullable=True),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index("ix_pending_approvals_case_id", "pending_approvals", ["case_id"])
    op.create_index("ix_pending_approvals_merchant_id", "pending_approvals", ["merchant_id"])


def downgrade() -> None:
    op.drop_index("ix_pending_approvals_merchant_id", table_name="pending_approvals")
    op.drop_index("ix_pending_approvals_case_id", table_name="pending_approvals")
    op.drop_table("pending_approvals")
    op.drop_index("ix_staged_actions_merchant_id", table_name="staged_actions")
    op.drop_index("ix_staged_actions_case_id", table_name="staged_actions")
    op.drop_table("staged_actions")
