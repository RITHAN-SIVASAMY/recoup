"""FR-12 against a real event store and the link_redemptions/customer_opt_outs
tables: the full recovery flow — view, pay, opt out, remind later — and the
single-use/expiry/opt-out-propagation guarantees each of those depends on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.factories import case_created_payload

from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor
from recoup.execution import recovery
from recoup.execution.links import LinkRedemptionStore, generate_link_token
from recoup.execution.optout import OptOutStore
from recoup.execution.payment_links import SimulatorPaymentLinkPort

pytestmark = pytest.mark.integration

SYSTEM = Actor(kind="system", identifier="test")
_SECRET = "test-signing-secret"
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
_TTL = timedelta(hours=72)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine()
    yield eng
    await eng.dispose()


async def _seeded_case(
    store: EventStore,
    *,
    customer_ref: str | None = None,
    root_cause: str = "card_expired_or_invalid",
) -> str:
    case_id = new_ulid()
    overrides: dict[str, str] = {"amount_at_risk": "499.00"}
    if customer_ref is not None:
        overrides["customer_ref"] = customer_ref
    payload = case_created_payload(**overrides)
    await store.append(case_id=case_id, event_type="case.created", payload=payload, actor=SYSTEM)
    await store.append(
        case_id=case_id,
        event_type="case.classified",
        payload={"root_cause": root_cause, "confidence": 0.9},
        actor=SYSTEM,
    )
    return case_id


def _token(case_id: str, ladder_step: int = 1, *, now: datetime = _NOW) -> str:
    return generate_link_token(case_id, ladder_step, secret=_SECRET, ttl=_TTL, now=now)


async def test_resolving_a_valid_link_returns_the_cause_specific_fix(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = await _seeded_case(store, root_cause="card_expired_or_invalid")
    token = _token(case_id)

    ctx = await recovery.resolve_link(
        token,
        event_store=store,
        redemption_store=LinkRedemptionStore(engine),
        secret=_SECRET,
        now=_NOW,
    )

    assert ctx.case.case_id == case_id
    assert ctx.fix.kind == "update_card"

    events = await store.events_for(case_id)
    assert events[-1].event_type == "link.viewed"


async def test_resolving_an_expired_link_raises(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    case_id = await _seeded_case(store)
    token = _token(case_id)

    with pytest.raises(recovery.RecoveryLinkExpiredError):
        await recovery.resolve_link(
            token,
            event_store=store,
            redemption_store=LinkRedemptionStore(engine),
            secret=_SECRET,
            now=_NOW + _TTL + timedelta(seconds=1),
        )


async def test_the_full_pay_flow_marks_the_case_recovered_and_the_link_single_use(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    redemption_store = LinkRedemptionStore(engine)
    case_id = await _seeded_case(store)
    token = _token(case_id)

    result = await recovery.complete_payment(
        token,
        event_store=store,
        redemption_store=redemption_store,
        payment_link_port=SimulatorPaymentLinkPort("http://localhost:3000"),
        secret=_SECRET,
        amount_inr=Decimal("499.00"),
        callback_url=f"http://localhost:3000/r/{token}/simulate-payment",
        now=_NOW,
    )
    assert result.checkout_url

    await recovery.confirm_payment(
        token,
        event_store=store,
        redemption_store=redemption_store,
        secret=_SECRET,
        provider_ref="sim-ref-1",
        now=_NOW,
    )

    events = await store.events_for(case_id)
    assert events[-1].event_type == "payment.recovered"

    with pytest.raises(recovery.RecoveryLinkAlreadyUsedError):
        await recovery.confirm_payment(
            token,
            event_store=store,
            redemption_store=redemption_store,
            secret=_SECRET,
            provider_ref="sim-ref-2",
            now=_NOW,
        )


async def test_opting_out_propagates_to_a_second_case_for_the_same_customer(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    redemption_store = LinkRedemptionStore(engine)
    optout_store = OptOutStore(engine)
    shared_customer = f"cust-{new_ulid()}"

    first_case_id = await _seeded_case(store, customer_ref=shared_customer)
    await recovery.record_opt_out(
        _token(first_case_id),
        event_store=store,
        redemption_store=redemption_store,
        optout_store=optout_store,
        secret=_SECRET,
        now=_NOW,
    )

    assert await optout_store.is_opted_out(shared_customer) is True

    # A second, unrelated case for the same customer inherits the opt-out —
    # REG-COMM-03's "across all cases", checked at the customer level.
    second_case_id = await _seeded_case(store, customer_ref=shared_customer)
    assert await optout_store.is_opted_out(shared_customer) is True
    assert second_case_id != first_case_id


async def test_remind_later_rejects_a_past_or_too_distant_date(engine: AsyncEngine) -> None:
    store = EventStore(engine)
    redemption_store = LinkRedemptionStore(engine)
    case_id = await _seeded_case(store)

    with pytest.raises(ValueError, match="future"):
        await recovery.record_remind_later(
            _token(case_id),
            event_store=store,
            redemption_store=redemption_store,
            secret=_SECRET,
            remind_at=date(2025, 1, 1),
            now=_NOW,
        )

    with pytest.raises(ValueError, match="too far"):
        await recovery.record_remind_later(
            _token(case_id, ladder_step=2, now=_NOW),
            event_store=store,
            redemption_store=redemption_store,
            secret=_SECRET,
            remind_at=date(2027, 1, 1),
            now=_NOW,
        )


async def test_remind_later_records_the_chosen_date_and_consumes_the_link(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    redemption_store = LinkRedemptionStore(engine)
    case_id = await _seeded_case(store)
    token = _token(case_id)

    await recovery.record_remind_later(
        token,
        event_store=store,
        redemption_store=redemption_store,
        secret=_SECRET,
        remind_at=date(2026, 1, 10),
        now=_NOW,
    )

    events = await store.events_for(case_id)
    assert events[-1].event_type == "case.remind_later"
    assert events[-1].payload["remind_at"] == "2026-01-10"

    with pytest.raises(recovery.RecoveryLinkAlreadyUsedError):
        await recovery.record_opt_out(
            token,
            event_store=store,
            redemption_store=redemption_store,
            optout_store=OptOutStore(engine),
            secret=_SECRET,
            now=_NOW,
        )


async def test_switching_the_displayed_method_does_not_consume_the_link(
    engine: AsyncEngine,
) -> None:
    store = EventStore(engine)
    redemption_store = LinkRedemptionStore(engine)
    case_id = await _seeded_case(store)
    token = _token(case_id)

    await recovery.switch_method(
        token, event_store=store, secret=_SECRET, to_channel="email", now=_NOW
    )
    assert await redemption_store.is_redeemed(token) is False

    # still usable for a real terminal action afterward
    await recovery.record_opt_out(
        token,
        event_store=store,
        redemption_store=redemption_store,
        optout_store=OptOutStore(engine),
        secret=_SECRET,
        now=_NOW,
    )
    assert await redemption_store.is_redeemed(token) is True
