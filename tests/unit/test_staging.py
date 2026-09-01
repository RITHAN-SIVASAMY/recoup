"""Unit tests for `execution/staging.py`'s pure functions — no I/O, no event loop."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from recoup.domain.models import Actor
from recoup.execution.staging import (
    StagedAction,
    _undo_window,
    cancel,
    is_due_for_promotion,
    promote,
)
from recoup.policy.schema import MerchantStaging

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
_STAGING = MerchantStaging(
    contact_undo_window=timedelta(seconds=60), money_undo_window=timedelta(minutes=5)
)
_HUMAN = Actor(kind="human", identifier="ops-1")


def _staged(**overrides: object) -> StagedAction:
    defaults: dict[str, object] = {
        "staged_action_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "case_id": "01ARZ3NDEKTSV4RRFFQ69G5FAW",
        "merchant_id": "demo",
        "action_type": "send_message",
        "channel": "sms",
        "ladder_step": 1,
        "idempotency_key": "deadbeef",
        "estimated_cost_inr": Decimal("0.20"),
        "policy_version": "abc123",
        "staged_at": _NOW,
        "promote_at": _NOW + timedelta(seconds=60),
    }
    defaults.update(overrides)
    return StagedAction(**defaults)  # type: ignore[arg-type]


def test_undo_window_is_5_minutes_for_a_money_moving_action() -> None:
    assert _undo_window("retry_charge", _STAGING) == timedelta(minutes=5)


def test_undo_window_is_60_seconds_for_a_contact_action() -> None:
    assert _undo_window("send_message", _STAGING) == timedelta(seconds=60)
    assert _undo_window("stop", _STAGING) == timedelta(seconds=60)


def test_cancel_transitions_a_staged_action_to_cancelled() -> None:
    cancelled = cancel(_staged(), actor=_HUMAN, now=_NOW)
    assert cancelled.status == "cancelled"
    assert cancelled.cancelled_at == _NOW
    assert cancelled.cancelled_by == _HUMAN


def test_cancel_refuses_an_action_that_is_not_staged() -> None:
    already_cancelled = _staged(status="cancelled")
    with pytest.raises(ValueError, match="cannot cancel"):
        cancel(already_cancelled, actor=_HUMAN, now=_NOW)


def test_promote_refuses_an_action_that_is_not_staged() -> None:
    already_promoted = _staged(status="promoted")
    with pytest.raises(ValueError, match="cannot promote"):
        promote(already_promoted)


def test_promote_transitions_a_staged_action_to_promoted() -> None:
    promoted = promote(_staged())
    assert promoted.status == "promoted"


def test_is_due_for_promotion_is_false_before_the_window_elapses() -> None:
    staged = _staged(promote_at=_NOW + timedelta(seconds=60))
    assert is_due_for_promotion(staged, now=_NOW) is False


def test_is_due_for_promotion_is_true_once_the_window_elapses() -> None:
    staged = _staged(promote_at=_NOW - timedelta(seconds=1))
    assert is_due_for_promotion(staged, now=_NOW) is True


def test_is_due_for_promotion_is_false_for_a_cancelled_action_even_past_its_window() -> None:
    staged = _staged(status="cancelled", promote_at=_NOW - timedelta(seconds=1))
    assert is_due_for_promotion(staged, now=_NOW) is False
