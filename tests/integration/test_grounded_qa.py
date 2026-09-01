"""FR-14.5/14.6/CON-04, against a real Postgres event log. `ask()`'s
`drafter` parameter is injected with a stub in every test here so the
citation-validation and refusal contract is proven deterministically,
without depending on a live model or a real API key.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.audit.event_store import EventStore, create_engine
from recoup.audit.qa import ask
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor
from recoup.llm.schemas import GroundedAnswer

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def _seed_case(engine: AsyncEngine) -> str:
    store = EventStore(engine)
    case_id = new_ulid()
    await store.append(
        case_id=case_id,
        event_type="case.created",
        payload=case_created_payload(),
        actor=SYSTEM,
    )
    await store.append(
        case_id=case_id,
        event_type="voice.call_started",
        payload={"channel": "voice"},
        actor=SYSTEM,
    )
    return case_id


async def test_a_valid_grounded_answer_with_matching_citations_passes_through(
    engine: AsyncEngine,
) -> None:
    case_id = await _seed_case(engine)
    events = await EventStore(engine).events_for(case_id)
    cited_id = events[0].event_id

    async def stub_drafter(_question: str, _events: object) -> GroundedAnswer:
        return GroundedAnswer(
            answer=f"The case was created. [event:{cited_id}]",
            citations=[cited_id],
            refused=False,
        )

    result = await ask(
        engine, case_id=case_id, question="what happened", now=_NOW, drafter=stub_drafter
    )

    assert result.refused is False
    assert result.degraded_mode is False
    assert result.citations == (cited_id,)


async def test_a_citation_to_an_event_never_shown_to_the_model_falls_back_to_summary(
    engine: AsyncEngine,
) -> None:
    case_id = await _seed_case(engine)
    fabricated_id = new_ulid()  # a real-looking ULID, but never retrieved

    async def stub_drafter(_question: str, _events: object) -> GroundedAnswer:
        return GroundedAnswer(
            answer=f"Something happened. [event:{fabricated_id}]",
            citations=[fabricated_id],
            refused=False,
        )

    result = await ask(
        engine, case_id=case_id, question="what happened", now=_NOW, drafter=stub_drafter
    )

    assert result.degraded_mode is True
    assert fabricated_id not in result.citations


async def test_inline_citations_disagreeing_with_the_structured_list_falls_back(
    engine: AsyncEngine,
) -> None:
    case_id = await _seed_case(engine)
    events = await EventStore(engine).events_for(case_id)
    cited_id = events[0].event_id
    other_id = events[1].event_id

    async def stub_drafter(_question: str, _events: object) -> GroundedAnswer:
        # inline marker cites `cited_id`, structured list claims `other_id` — disagreement.
        return GroundedAnswer(
            answer=f"Something happened. [event:{cited_id}]",
            citations=[other_id],
            refused=False,
        )

    result = await ask(
        engine, case_id=case_id, question="what happened", now=_NOW, drafter=stub_drafter
    )

    assert result.degraded_mode is True


async def test_a_case_with_zero_events_refuses_without_ever_calling_the_model(
    engine: AsyncEngine,
) -> None:
    case_id = new_ulid()  # never seeded, no events at all
    called = False

    async def stub_drafter(_question: str, _events: object) -> GroundedAnswer | None:
        nonlocal called
        called = True
        return None

    result = await ask(
        engine, case_id=case_id, question="what happened", now=_NOW, drafter=stub_drafter
    )

    assert result.refused is True
    assert called is False


async def test_drafter_returning_none_degrades_to_a_deterministic_summary(
    engine: AsyncEngine,
) -> None:
    case_id = await _seed_case(engine)

    async def stub_drafter(_question: str, _events: object) -> GroundedAnswer | None:
        return None

    result = await ask(
        engine, case_id=case_id, question="what happened", now=_NOW, drafter=stub_drafter
    )

    assert result.degraded_mode is True
    assert result.refused is False
    assert len(result.citations) > 0  # the raw retrieved events, listed


async def test_a_refusal_that_still_carries_citations_is_treated_as_untrustworthy(
    engine: AsyncEngine,
) -> None:
    case_id = await _seed_case(engine)
    events = await EventStore(engine).events_for(case_id)
    cited_id = events[0].event_id

    async def stub_drafter(_question: str, _events: object) -> GroundedAnswer:
        return GroundedAnswer(
            answer=f"Not sure, but see [event:{cited_id}]",
            citations=[cited_id],
            refused=True,
            refusal_reason="unclear",
        )

    result = await ask(
        engine, case_id=case_id, question="what happened", now=_NOW, drafter=stub_drafter
    )

    assert result.degraded_mode is True
    assert result.refused is False  # the fallback path never refuses; it summarizes instead


async def test_a_clean_refusal_with_no_citations_passes_through(engine: AsyncEngine) -> None:
    case_id = await _seed_case(engine)

    async def stub_drafter(_question: str, _events: object) -> GroundedAnswer:
        return GroundedAnswer(
            answer="",
            citations=[],
            refused=True,
            refusal_reason="the log does not record the customer's credit score",
        )

    result = await ask(
        engine,
        case_id=case_id,
        question="what is their credit score",
        now=_NOW,
        drafter=stub_drafter,
    )

    assert result.refused is True
    assert result.refusal_reason == "the log does not record the customer's credit score"
    assert result.degraded_mode is False
