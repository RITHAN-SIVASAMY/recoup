"""Unit tests for the pure fold/project functions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.factories import case_created_payload

from recoup.audit.hashchain import GENESIS_HASH, compute_hash
from recoup.audit.projection import fold, project
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor, CaseEvent

pytestmark = pytest.mark.unit

SYSTEM = Actor(kind="system", identifier="test")


def _event(case_id: str, seq: int, event_type: str, payload: dict, prev_hash: str) -> CaseEvent:
    occurred_at = datetime(2026, 1, 1, tzinfo=UTC)
    return CaseEvent(
        event_id=new_ulid(),
        case_id=case_id,
        seq=seq,
        occurred_at=occurred_at,
        recorded_at=occurred_at,
        actor=SYSTEM,
        event_type=event_type,
        payload=payload,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, payload, seq, occurred_at),
    )


def test_fold_applies_case_created_first() -> None:
    case_id = new_ulid()
    created = _event(case_id, 1, "case.created", case_created_payload(), GENESIS_HASH)

    case = fold(None, created)

    assert case.case_id == case_id
    assert case.source_type == "payment_failure"
    assert case.resolution_state == "pending"
    assert case.seq == 1
    assert case.tip_hash == created.hash


def test_fold_rejects_a_non_created_event_with_no_prior_case() -> None:
    case_id = new_ulid()
    stray = _event(case_id, 1, "case.exception", {}, GENESIS_HASH)

    with pytest.raises(ValueError, match=r"no case\.created event"):
        fold(None, stray)


def test_project_folds_events_in_seq_order_regardless_of_input_order() -> None:
    case_id = new_ulid()
    created = _event(
        case_id, 1, "case.created", case_created_payload("mandate_failure"), GENESIS_HASH
    )
    second = _event(case_id, 2, "case.exception", {}, created.hash)

    case_in_order = project([created, second])
    case_reversed = project([second, created])

    assert case_in_order == case_reversed
    assert case_in_order.seq == 2
    assert case_in_order.tip_hash == second.hash


def test_project_rejects_an_empty_stream() -> None:
    with pytest.raises(ValueError, match="empty event stream"):
        project([])
