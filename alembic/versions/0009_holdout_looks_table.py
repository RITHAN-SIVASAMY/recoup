"""holdout_looks table

FR-13.5/§6: "The full holdout schedule and every look are logged, so a
reviewer can verify the sequence was not chosen after seeing the data."
A look is a batch-level fact, not a per-case one, so it does not belong in
case_events (which is FK'd to a single case). append-only for the same
reason case_events is: a sequence a reviewer is meant to audit for
after-the-fact tampering must not be editable after the fact either.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION holdout_looks_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'holdout_looks is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""
_TRIGGER = """
CREATE TRIGGER holdout_looks_no_update_or_delete
    BEFORE UPDATE OR DELETE ON holdout_looks
    FOR EACH ROW EXECUTE FUNCTION holdout_looks_immutable();
"""


def upgrade() -> None:
    op.create_table(
        "holdout_looks",
        sa.Column("look_id", sa.String(length=26), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("look_index", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("information_fraction", sa.Numeric(6, 4), nullable=False),
        sa.Column("z_boundary", sa.Numeric(10, 4), nullable=False),
        sa.Column("alpha_spent", sa.Numeric(8, 6), nullable=False),
        sa.Column("z_observed", sa.Numeric(10, 4), nullable=False),
        sa.Column("lift", sa.Numeric(10, 6), nullable=False),
        sa.Column("ci_low", sa.Numeric(10, 6), nullable=False),
        sa.Column("ci_high", sa.Numeric(10, 6), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("rate_before", sa.Numeric(6, 4), nullable=False),
        sa.Column("rate_after", sa.Numeric(6, 4), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("look_id"),
        sa.UniqueConstraint("batch_id", "look_index", name="uq_holdout_looks_batch_index"),
    )
    op.create_index("ix_holdout_looks_batch_id", "holdout_looks", ["batch_id"])
    op.execute(_TRIGGER_FUNCTION)
    op.execute(_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS holdout_looks_no_update_or_delete ON holdout_looks;")
    op.execute("DROP FUNCTION IF EXISTS holdout_looks_immutable();")
    op.drop_index("ix_holdout_looks_batch_id", table_name="holdout_looks")
    op.drop_table("holdout_looks")
