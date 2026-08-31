"""cases and case_events tables

Revision ID: 0001
Revises:
Create Date: 2026-08-31 15:33:27.796362

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# case_events is the source of truth; nothing may UPDATE or DELETE a row once written.
_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION case_events_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'case_events is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""
_TRIGGER = """
CREATE TRIGGER case_events_no_update_or_delete
    BEFORE UPDATE OR DELETE ON case_events
    FOR EACH ROW EXECUTE FUNCTION case_events_immutable();
"""


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("case_id", sa.String(length=26), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("resolution_state", sa.String(length=32), nullable=False),
        sa.Column("cohort", sa.String(length=16), nullable=True),
        sa.Column("root_cause", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("tip_hash", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("case_id"),
    )
    op.create_table(
        "case_events",
        sa.Column("event_id", sa.String(length=26), nullable=False),
        sa.Column("case_id", sa.String(length=26), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=True),
        sa.Column("model_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"]),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("case_id", "seq", name="uq_case_events_case_seq"),
        sa.UniqueConstraint("idempotency_key", name="uq_case_events_idempotency_key"),
    )
    op.create_index("ix_case_events_event_type", "case_events", ["event_type"], unique=False)
    op.execute(_TRIGGER_FUNCTION)
    op.execute(_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS case_events_no_update_or_delete ON case_events;")
    op.execute("DROP FUNCTION IF EXISTS case_events_immutable();")
    op.drop_index("ix_case_events_event_type", table_name="case_events")
    op.drop_table("case_events")
    op.drop_table("cases")
