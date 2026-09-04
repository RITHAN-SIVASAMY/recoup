"""FR-12.2: every diagnosable root cause maps to a specific, correct fix —
never a generic "please try again"."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from recoup.execution.recovery import fix_for

pytestmark = pytest.mark.unit

_EXPECTED_KIND = {
    "card_expired_or_invalid": "update_card",
    "insufficient_funds": "retry",
    "otp_timeout_or_auth_abandon": "retry",
    "mandate_revoked": "reauthorize",
    "checkout_abandonment": "resume_cart",
    "receivable_overdue": "pay_invoice",
}


@pytest.mark.parametrize(("root_cause", "expected_kind"), list(_EXPECTED_KIND.items()))
def test_each_diagnosable_root_cause_gets_its_specific_fix(
    root_cause: str, expected_kind: str
) -> None:
    fix = fix_for(root_cause)
    assert fix.kind == expected_kind


def test_every_ladder_root_cause_has_a_defined_fix_not_the_generic_fallback() -> None:
    raw = Path("policies/ladders.yaml").read_text(encoding="utf-8")
    ladders = yaml.safe_load(raw)["ladders"]
    for root_cause in ladders:
        if root_cause == "unknown":
            continue
        fix = fix_for(root_cause)
        assert fix.kind != "contact_support" or root_cause == "issuer_risk_block", (
            f"{root_cause} silently fell back to the generic fix"
        )


def test_an_unrecognized_root_cause_gets_the_generic_fallback_not_a_crash() -> None:
    fix = fix_for("something_never_seen_before")
    assert fix.kind == "contact_support"


def test_a_none_root_cause_gets_the_generic_fallback() -> None:
    fix = fix_for(None)
    assert fix.kind == "contact_support"
