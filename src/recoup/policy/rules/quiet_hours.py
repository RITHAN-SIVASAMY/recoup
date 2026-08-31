"""REG-COMM-01: no commercial contact outside the permitted hours.

`start`/`end` describe the *permitted* window (default 09:00-20:00 IST); anything
outside it is quiet hours. Written to handle a wrapping window (start > end, e.g.
an overnight permitted band) even though the shipped default doesn't need it, and
tested across a DST-observing timezone even though Asia/Kolkata itself has none —
so a merchant configuring a different tz doesn't silently break this rule.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from recoup.policy.schema import QuietHours


def _parse_time_of_day(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def is_within_permitted_hours(now: datetime, quiet_hours: QuietHours) -> bool:
    local_now = now.astimezone(ZoneInfo(quiet_hours.tz))
    start = _parse_time_of_day(quiet_hours.start)
    end = _parse_time_of_day(quiet_hours.end)
    local_time = local_now.time()

    if start <= end:
        return start <= local_time < end
    return local_time >= start or local_time < end  # wraps past midnight
