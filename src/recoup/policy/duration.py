"""A minimal ISO 8601 duration parser — just enough for `policies/*.yaml`'s
`wait_before`/`window`/`min_gap` fields (P<n>D, PT<n>H, PT<n>M, PT<n>S, PT0S,
and combinations like P2DT12H). Pulling in a dependency for six duration
patterns isn't worth it; this is deliberately not a general ISO 8601 parser.
"""

from __future__ import annotations

import re
from datetime import timedelta

_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_duration(value: str) -> timedelta:
    match = _PATTERN.match(value)
    if not match or not any(match.groups()):
        raise ValueError(f"unsupported ISO 8601 duration: {value!r}")
    parts = {key: int(val) for key, val in match.groupdict().items() if val is not None}
    return timedelta(
        days=parts.get("days", 0),
        hours=parts.get("hours", 0),
        minutes=parts.get("minutes", 0),
        seconds=parts.get("seconds", 0),
    )
