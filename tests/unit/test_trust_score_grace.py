"""FR-11.2: escalation stays suspended through promised_date + grace."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from recoup.understanding.trust import DEFAULT_GRACE, is_within_grace

pytestmark = pytest.mark.unit

_PROMISED = datetime(2026, 1, 10, tzinfo=UTC)


def test_still_within_grace_on_the_promised_date_itself() -> None:
    assert is_within_grace(_PROMISED, now=_PROMISED) is True


def test_still_within_grace_just_before_the_window_closes() -> None:
    assert is_within_grace(_PROMISED, now=_PROMISED + DEFAULT_GRACE) is True


def test_no_longer_within_grace_once_the_window_has_passed() -> None:
    assert is_within_grace(_PROMISED, now=_PROMISED + DEFAULT_GRACE + timedelta(seconds=1)) is False


def test_a_narrower_grace_can_be_supplied_for_a_lower_trust_customer() -> None:
    narrow = timedelta(hours=6)
    assert is_within_grace(_PROMISED, now=_PROMISED + timedelta(hours=12), grace=narrow) is False
