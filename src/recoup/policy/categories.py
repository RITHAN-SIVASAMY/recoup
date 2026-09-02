"""Human-facing category labels for policy rule IDs (FR-15.6's compliance
view, and `demo.py`'s batch-simulation blocked-action tally both read this
same mapping -- one source of truth for "which rule means what" in the UI).
"""

from __future__ import annotations

RULE_CATEGORY: dict[str, str] = {
    "REG-COMM-01": "quiet_hours",
    "REG-COMM-02": "no_consent",
    "REG-COMM-03": "opt_out",
    "REG-COMM-06": "cap",
    "REG-MAND-01": "mandate",
    "REG-MAND-02": "mandate",
    "REG-MAND-03": "mandate",
    "REG-MAND-04": "mandate",
    "RULE-CTRL-001": "control_cohort",
    "RULE-EXPOSURE-001": "exposure_cap",
    "RULE-STOP-TERMINAL": "terminal",
    "RULE-LADDER-FORBIDDEN": "ladder",
    "RULE-LADDER-SEQUENCE": "ladder",
    "RULE-LADDER-CHANNEL": "ladder",
    "RULE-KILL-001": "kill_switch",
    "RULE-DUP-001": "duplicate",
    "RULE-APPROVAL-ALWAYS": "approval_required",
    "RULE-APPROVAL-VALUE": "approval_required",
    "RULE-APPROVAL-FLAGGED": "approval_required",
}


def category_for(rule_id: str) -> str:
    return RULE_CATEGORY.get(rule_id, "other")
