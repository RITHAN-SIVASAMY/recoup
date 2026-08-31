"""Pure projection: fold a case's events into its current `Case` state.

`project()` and `fold()` are used both by `EventStore.append` (incremental,
one event at a time) and by `rebuild_all()` (from scratch, for `make
replay`) — the same functions, so the two paths cannot drift apart.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

from recoup.domain.canonical import canonical_json
from recoup.domain.models import Case, CaseEvent, SourceType


def fold(case: Case | None, event: CaseEvent) -> Case:
    if event.event_type == "case.created":
        return Case(
            case_id=event.case_id,
            source_type=cast(SourceType, event.payload["source_type"]),
            resolution_state="pending",
            cohort=None,
            root_cause=None,
            created_at=event.occurred_at,
            updated_at=event.occurred_at,
            seq=event.seq,
            tip_hash=event.hash,
        )
    if case is None:
        raise ValueError(
            f"cannot apply {event.event_type!r} to case {event.case_id}: "
            "no case.created event has been folded yet"
        )
    return case.model_copy(
        update={"updated_at": event.occurred_at, "seq": event.seq, "tip_hash": event.hash}
    )


def project(events: Sequence[CaseEvent]) -> Case:
    if not events:
        raise ValueError("cannot project an empty event stream")
    case: Case | None = None
    for event in sorted(events, key=lambda e: e.seq):
        case = fold(case, event)
    assert case is not None  # the loop above always assigns at least once
    return case


def rebuild_all(events: Sequence[CaseEvent]) -> dict[str, Case]:
    by_case: dict[str, list[CaseEvent]] = defaultdict(list)
    for event in events:
        by_case[event.case_id].append(event)
    return {case_id: project(case_events) for case_id, case_events in by_case.items()}


@dataclass(frozen=True)
class ReplayResult:
    matches: bool
    cases_checked: int
    diverging_case_ids: tuple[str, ...] = field(default_factory=tuple)


def diff_against_stored(rebuilt: dict[str, Case], stored: dict[str, Case]) -> ReplayResult:
    """Byte-for-byte comparison (canonical JSON) between a rebuilt and a stored projection."""
    diverging = tuple(
        case_id
        for case_id, case in rebuilt.items()
        if case_id not in stored
        or canonical_json(case.model_dump(mode="json"))
        != canonical_json(stored[case_id].model_dump(mode="json"))
    )
    return ReplayResult(
        matches=not diverging, cases_checked=len(rebuilt), diverging_case_ids=diverging
    )
