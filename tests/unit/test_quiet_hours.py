"""REG-COMM-01 unit tests: timezone edges, DST transitions, and midnight wraps.

Asia/Kolkata itself observes no DST, so a DST-transition test needs a different
tz to be meaningful — proving the rule's *logic* is DST-safe, which matters the
moment a merchant configures a different timezone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from recoup.policy.rules.quiet_hours import is_within_permitted_hours
from recoup.policy.schema import QuietHours

pytestmark = pytest.mark.unit

IST_HOURS = QuietHours(start="09:00", end="20:00", tz="Asia/Kolkata")


def test_within_business_hours_ist_is_permitted() -> None:
    # 12:00 IST == 06:30 UTC
    now = datetime(2026, 1, 2, 6, 30, tzinfo=ZoneInfo("UTC"))
    assert is_within_permitted_hours(now, IST_HOURS) is True


def test_before_business_hours_ist_is_quiet() -> None:
    # 08:59 IST == 03:29 UTC
    now = datetime(2026, 1, 2, 3, 29, tzinfo=ZoneInfo("UTC"))
    assert is_within_permitted_hours(now, IST_HOURS) is False


def test_at_the_end_boundary_is_quiet_end_is_exclusive() -> None:
    now = datetime(2026, 1, 2, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert is_within_permitted_hours(now, IST_HOURS) is False


def test_at_the_start_boundary_is_permitted_start_is_inclusive() -> None:
    now = datetime(2026, 1, 2, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert is_within_permitted_hours(now, IST_HOURS) is True


def test_naive_utc_input_is_converted_correctly_across_the_ist_offset() -> None:
    # 23:30 UTC == 05:00 IST the next day — quiet hours, not permitted.
    now = datetime(2026, 1, 1, 23, 30, tzinfo=UTC)
    assert is_within_permitted_hours(now, IST_HOURS) is False


def test_midnight_wrap_when_the_permitted_window_itself_wraps_past_midnight() -> None:
    # A permitted window of 22:00-06:00 (wraps past midnight).
    overnight = QuietHours(start="22:00", end="06:00", tz="Asia/Kolkata")
    just_after_midnight = datetime(2026, 1, 2, 1, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    just_before_start = datetime(2026, 1, 2, 21, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
    mid_afternoon = datetime(2026, 1, 2, 14, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    assert is_within_permitted_hours(just_after_midnight, overnight) is True
    assert is_within_permitted_hours(just_before_start, overnight) is False
    assert is_within_permitted_hours(mid_afternoon, overnight) is False


def test_dst_spring_forward_us_eastern_does_not_shift_the_permitted_window() -> None:
    # 2026-03-08 is US Eastern's spring-forward date. 10:00 local before and
    # after the transition must both read as "within 09:00-20:00" — the local
    # wall-clock hour is what matters, not the UTC offset behind it.
    hours = QuietHours(start="09:00", end="20:00", tz="America/New_York")
    before_transition = datetime(2026, 3, 7, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    after_transition = datetime(2026, 3, 9, 10, 0, tzinfo=ZoneInfo("America/New_York"))

    assert is_within_permitted_hours(before_transition, hours) is True
    assert is_within_permitted_hours(after_transition, hours) is True


def test_dst_fall_back_us_eastern_does_not_shift_the_permitted_window() -> None:
    # 2026-11-01 is US Eastern's fall-back date.
    hours = QuietHours(start="09:00", end="20:00", tz="America/New_York")
    before_transition = datetime(2026, 10, 31, 19, 30, tzinfo=ZoneInfo("America/New_York"))
    after_transition = datetime(2026, 11, 2, 19, 30, tzinfo=ZoneInfo("America/New_York"))

    assert is_within_permitted_hours(before_transition, hours) is True
    assert is_within_permitted_hours(after_transition, hours) is True
