"""FR-14.7: the 40-question grounded Q&A golden set, evaluated against the
live model. Two gates, both explicit in the phase spec:

1. Zero fabricated citations, ever — every citation `ask()` returns must
   reference an event actually seeded for that case. `ask()` already
   guarantees this structurally (see `test_grounded_qa_invariants.py`), but
   this test re-checks it end to end against the live model output, per the
   phase's own "validated programmatically before the answer is returned".
2. Refusal rate on the deliberately-unanswerable half must be >= 95% — a
   missed refusal here means the model answered a question the log cannot
   support, which is the one failure mode this whole phase exists to catch.

Gated on a live `ANTHROPIC_API_KEY`, same as `tests/llm_eval`'s other suites.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.audit.event_store import EventStore, create_engine
from recoup.audit.qa import ask
from recoup.domain.ids import Ulid, new_ulid
from recoup.domain.models import Actor
from recoup.settings import get_settings

pytestmark = [
    pytest.mark.llm_eval,
    pytest.mark.skipif(
        not get_settings().anthropic_api_key, reason="no ANTHROPIC_API_KEY configured"
    ),
]

_GOLDEN_PATH = Path(__file__).parent / "grounded_qa.jsonl"
_NOW = datetime(2026, 1, 5, tzinfo=UTC)
SYSTEM = Actor(kind="system", identifier="test")

# CI gates, per the phase spec verbatim: any fabricated citation fails the
# build outright; the refusal floor on the unanswerable half is 95%.
_MIN_REFUSAL_RATE_ON_UNANSWERABLE = 0.95

# case_key -> the deterministic event history seeded for it before the eval runs.
_SCENARIOS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "A": [
        ("case.created", case_created_payload("payment_failure", amount_at_risk="499.00")),
        ("action.sent", {"channel": "sms", "template": "reminder_1"}),
        ("action.delivered", {"channel": "sms"}),
        ("action.sent", {"channel": "sms", "template": "reminder_2"}),
        ("voice.call_started", {"channel": "voice"}),
        ("ptp.captured", {"amount": "499.00", "promised_date": "2026-01-10"}),
        ("voice.call_ended", {"duration_s": 120}),
        ("ptp.kept", {}),
        ("payment.recovered", {"amount": "499.00"}),
    ],
    "B": [
        ("case.created", case_created_payload("checkout_abandonment")),
        ("policy.denied", {"reason": "quiet_hours", "action": "call"}),
        ("case.exception", {"reason": "manual review needed"}),
    ],
    "C": [
        ("case.created", case_created_payload("mandate_lapse")),
        ("action.sent", {"channel": "email", "template": "reminder_1"}),
        ("customer.opted_out", {"channel": "email"}),
    ],
}


@dataclass(frozen=True)
class GoldenCase:
    case_key: str
    question: str
    expected_answerable: bool
    category: str


def _load_golden_set() -> list[GoldenCase]:
    cases = []
    with _GOLDEN_PATH.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            cases.append(
                GoldenCase(
                    case_key=row["case_key"],
                    question=row["question"],
                    expected_answerable=bool(row["expected_answerable"]),
                    category=row["category"],
                )
            )
    return cases


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def _seed_scenarios(engine: AsyncEngine) -> dict[str, tuple[Ulid, set[str]]]:
    store = EventStore(engine)
    seeded: dict[str, tuple[Ulid, set[str]]] = {}
    for case_key, event_specs in _SCENARIOS.items():
        case_id = new_ulid()
        event_ids: set[str] = set()
        for event_type, payload in event_specs:
            event = await store.append(
                case_id=case_id, event_type=event_type, payload=payload, actor=SYSTEM
            )
            event_ids.add(event.event_id)
        seeded[case_key] = (case_id, event_ids)
    return seeded


async def test_grounded_qa_citations_never_fabricated_and_refusal_rate_holds(
    engine: AsyncEngine,
) -> None:
    cases = _load_golden_set()
    assert len(cases) >= 40, "golden set must have at least 40 labelled questions (FR-14.7)"

    seeded = await _seed_scenarios(engine)

    unanswerable_total = unanswerable_refused = 0
    fabricated: list[str] = []
    missed_refusals: list[str] = []

    for case in cases:
        case_id, valid_event_ids = seeded[case.case_key]
        result = await ask(engine, case_id=case_id, question=case.question, now=_NOW)

        # Gate 1: no citation may reference an event outside this case's own
        # seeded history — a citation to a real event from a *different* case
        # would be a cross-case leak, just as dangerous as an invented ID.
        for citation in result.citations:
            if citation not in valid_event_ids:
                fabricated.append(f"{case.case_key}/{case.question!r} -> {citation}")

        if not case.expected_answerable:
            unanswerable_total += 1
            if result.refused:
                unanswerable_refused += 1
            else:
                missed_refusals.append(f"{case.category}: {case.question!r} -> {result.answer!r}")

    refusal_rate = unanswerable_refused / unanswerable_total if unanswerable_total else 1.0

    report = (
        f"refusal_rate={refusal_rate:.2f} ({unanswerable_refused}/{unanswerable_total})\n"
        f"fabricated or cross-case citations (must be empty): {fabricated}\n"
        f"missed refusals on unanswerable questions: {missed_refusals}"
    )

    assert not fabricated, report
    assert refusal_rate >= _MIN_REFUSAL_RATE_ON_UNANSWERABLE, report
