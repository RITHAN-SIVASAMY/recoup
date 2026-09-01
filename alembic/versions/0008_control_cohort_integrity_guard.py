"""control cohort integrity guard

FR-13.2: "A control case receives zero agent-initiated contact or retry. An
invariant test proves no action can attach to a control case." The policy
engine's RULE-CTRL-001 already denies every action against a control case
at the application layer; this is the second, independent layer -- a DB
trigger that makes it structurally impossible for a row to land in
staged_actions for a case whose cohort is 'control', even if a future bug
bypassed policy.evaluate() entirely.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-01 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION staged_actions_forbid_control_cohort() RETURNS trigger AS $$
BEGIN
    IF (SELECT cohort FROM cases WHERE case_id = NEW.case_id) = 'control' THEN
        RAISE EXCEPTION
            'staged_actions: case % is in the control cohort -- zero agent-initiated contact permitted (FR-13.2)',
            NEW.case_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
_TRIGGER = """
CREATE TRIGGER staged_actions_no_control_cohort
    BEFORE INSERT ON staged_actions
    FOR EACH ROW EXECUTE FUNCTION staged_actions_forbid_control_cohort();
"""


def upgrade() -> None:
    op.execute(_TRIGGER_FUNCTION)
    op.execute(_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS staged_actions_no_control_cohort ON staged_actions;")
    op.execute("DROP FUNCTION IF EXISTS staged_actions_forbid_control_cohort();")
