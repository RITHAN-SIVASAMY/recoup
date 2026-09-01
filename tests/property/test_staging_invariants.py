"""FR-7.2's reversibility invariant, property-tested: from any `StagedAction`,
at most one of {cancel, promote} ever succeeds, and once a terminal status is
reached it is never possible to reach a different one — the state machine
behind "a staged action is cancelled inside its window and never sends" and
"the kill switch cancels everything in flight" (context/phase-05...).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.domain.models import Actor
from recoup.execution.staging import (
    StagedAction,
    StagedActionStatus,
    cancel,
    is_due_for_promotion,
    promote,
)

pytestmark = pytest.mark.property

_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
_HUMAN = Actor(kind="human", identifier="ops-1")

_statuses = st.sampled_from(["staged", "cancelled", "promoted"])


def _staged(status: StagedActionStatus) -> StagedAction:
    return StagedAction(
        staged_action_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        case_id="01ARZ3NDEKTSV4RRFFQ69G5FAW",
        merchant_id="demo",
        action_type="send_message",
        channel="sms",
        ladder_step=1,
        idempotency_key="deadbeef",
        estimated_cost_inr=Decimal("0.20"),
        policy_version="abc123",
        staged_at=_NOW,
        promote_at=_NOW + timedelta(seconds=60),
        status=status,
    )


@given(status=_statuses)
def test_cancel_only_ever_succeeds_from_staged(status: StagedActionStatus) -> None:
    action = _staged(status)
    if status == "staged":
        cancelled = cancel(action, actor=_HUMAN, now=_NOW)
        assert cancelled.status == "cancelled"
    else:
        with pytest.raises(ValueError):
            cancel(action, actor=_HUMAN, now=_NOW)


@given(status=_statuses)
def test_promote_only_ever_succeeds_from_staged(status: StagedActionStatus) -> None:
    action = _staged(status)
    if status == "staged":
        promoted = promote(action)
        assert promoted.status == "promoted"
    else:
        with pytest.raises(ValueError):
            promote(action)


@given(status=_statuses)
def test_a_terminal_status_never_becomes_due_for_promotion(status: StagedActionStatus) -> None:
    # promote_at is always in the past here, so only "staged" may ever be due.
    action = replace(_staged(status), promote_at=_NOW - timedelta(seconds=1))
    assert is_due_for_promotion(action, now=_NOW) == (status == "staged")


@given(status=_statuses)
def test_cancelling_then_promoting_never_both_succeed(status: StagedActionStatus) -> None:
    action = _staged(status)
    try:
        cancelled = cancel(action, actor=_HUMAN, now=_NOW)
    except ValueError:
        cancelled = None
    if cancelled is not None:
        with pytest.raises(ValueError):
            promote(cancelled)
