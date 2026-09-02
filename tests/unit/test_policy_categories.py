"""FR-15.6: rule_id -> human category label, shared by the compliance view
and demo.py's blocked-action tally."""

from __future__ import annotations

import pytest

from recoup.policy.categories import category_for

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("rule_id", "expected"),
    [
        ("REG-COMM-01", "quiet_hours"),
        ("REG-COMM-03", "opt_out"),
        ("REG-COMM-06", "cap"),
        ("REG-MAND-02", "mandate"),
        ("RULE-CTRL-001", "control_cohort"),
    ],
)
def test_known_rule_ids_map_to_their_category(rule_id: str, expected: str) -> None:
    assert category_for(rule_id) == expected


def test_an_unknown_rule_id_maps_to_other_rather_than_raising() -> None:
    assert category_for("RULE-SOMETHING-NEVER-SEEN") == "other"
