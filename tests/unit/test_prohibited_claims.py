"""CON-01: no pressure tactics, manufactured urgency, false consequence,
shaming, or third-party disclosure survives into a sent message.
"""

from __future__ import annotations

import pytest

from recoup.llm.safety.prohibited_claims import check_message_safety

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "body",
    [
        "Failure to pay may result in legal action against you.",
        "This is your final notice before we escalate.",
        "Pay now or face consequences.",
        "This will affect your CIBIL score.",
        "You should feel ashamed of missing this payment.",
        "We will inform your employer about this unpaid balance.",
    ],
)
def test_flags_a_prohibited_message(body: str) -> None:
    assert check_message_safety(body) != []


def test_a_polite_factual_reminder_passes_clean() -> None:
    body = "Hi, we noticed your payment of INR 499 didn't go through. Tap here to retry: [recovery link]"
    assert check_message_safety(body) == []


def test_returns_a_human_readable_reason_for_each_violation() -> None:
    violations = check_message_safety("Last warning: pay immediately or else.")
    assert any("urgency" in reason for reason in violations)
