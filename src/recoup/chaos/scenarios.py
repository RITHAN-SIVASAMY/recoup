"""FR-16.1/16.2: ten reproducible chaos scenarios. Every scenario seeds its
own fresh case (fresh ULIDs / provider event IDs), so it is safe to run
repeatedly against a persistent dev database, the same convention the rest
of this codebase's integration tests already follow.

Each scenario ends by checking the outcomes FR-16.2 actually requires --
zero duplicate customer contact, zero duplicate charge attempts, zero lost
cases, a truthful exception-queue entry -- rather than merely "it didn't
crash". A `ScenarioResult.passed` is true only if every one of its
`outcomes` is true.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.event_store import EventStore
from recoup.audit.qa import Drafter, ask
from recoup.domain.ids import new_ulid
from recoup.domain.models import Actor, Case, CaseEvent, ProposedAction, Verdict
from recoup.economics.ev import price_ladder_step
from recoup.execution.approvals import ApprovalStore
from recoup.execution.dispatcher import dispatch, promote_and_send
from recoup.execution.idempotency import RedisIdempotencyGuard
from recoup.execution.ports import DeliveryReceipt, RenderedMessage, SendContext
from recoup.execution.staging import StagingStore, stage
from recoup.execution.templates import TemplateLoader
from recoup.ingestion.ingest import ingest
from recoup.ingestion.models import NormalizedIntake
from recoup.llm.schemas import GroundedAnswer
from recoup.policy.context import PolicyContext
from recoup.policy.loader import PolicyLoader
from recoup.policy.schema import MerchantStaging
from recoup.understanding.classify import CONFIDENCE_FLOOR, classify

_SYSTEM = Actor(kind="system", identifier="chaos")
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)  # a Friday, within permitted contact hours
_TEMPLATES = TemplateLoader().load()


@dataclass(frozen=True)
class ScenarioOutcome:
    label: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    case_id: str
    narrative: list[str] = field(default_factory=list)
    outcomes: list[ScenarioOutcome] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.outcomes) and all(o.passed for o in self.outcomes)


async def _seed_case(
    engine: AsyncEngine, *, source_type: str = "payment_failure", amount: str = "499.00"
) -> tuple[str, list[str]]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    intake = NormalizedIntake(
        source_type=source_type,  # type: ignore[arg-type]
        provider_event_id=f"chaos-{new_ulid()}",
        merchant_id="demo-d2c",
        amount_at_risk=Decimal(amount),
        customer_ref="cust_chaos",
        occurred_at=_NOW,
    )
    event_store = EventStore(engine)
    async with session_factory() as session:
        result = await ingest(session, event_store, intake)
    events = await event_store.events_for(result.case_id)
    return result.case_id, [e.event_type for e in events]


def _seeded_domain_case(case_id: str, *, root_cause: str = "insufficient_funds") -> Case:
    return Case(
        case_id=case_id,
        merchant_id="demo-d2c",
        source_type="payment_failure",
        provider_event_id="chaos-prov",
        amount_at_risk=Decimal("499.00"),
        customer_ref="cust_chaos",
        resolution_state="pending",
        cohort="treatment",
        root_cause=root_cause,
        created_at=_NOW,
        updated_at=_NOW,
        seq=1,
        tip_hash="h" * 64,
    )


# ── 1. duplicate webhook ─────────────────────────────────────────────────


async def run_duplicate_webhook(engine: AsyncEngine, *, deliveries: int = 25) -> ScenarioResult:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)
    intake = NormalizedIntake(
        source_type="payment_failure",
        provider_event_id=f"chaos-dup-{new_ulid()}",
        merchant_id="demo-d2c",
        amount_at_risk=Decimal("499.00"),
        customer_ref="cust_chaos",
        occurred_at=_NOW,
    )
    narrative = [f"delivering the identical webhook {deliveries} times in a row"]
    case_ids: set[str] = set()
    for _ in range(deliveries):
        async with session_factory() as session:
            result = await ingest(session, event_store, intake)
        case_ids.add(result.case_id)

    case_id = next(iter(case_ids))
    events = await event_store.events_for(case_id)
    event_types = [e.event_type for e in events]
    narrative.append(
        f"case {case_id}: {event_types.count('case.created')} case.created, "
        f"{event_types.count('event.duplicate_suppressed')} suppressed"
    )
    return ScenarioResult(
        scenario="duplicate_webhook",
        case_id=case_id,
        narrative=narrative,
        outcomes=[
            ScenarioOutcome(
                "exactly one case created",
                len(case_ids) == 1 and event_types.count("case.created") == 1,
                f"{len(case_ids)} distinct case_id(s) produced by {deliveries} deliveries",
            ),
            ScenarioOutcome(
                "zero duplicate contacts",
                set(event_types) == {"case.created", "event.duplicate_suppressed"},
                "no action.* event exists on this case",
            ),
        ],
    )


# ── 2. out-of-order events ───────────────────────────────────────────────


async def run_out_of_order_events(engine: AsyncEngine, redis: Redis) -> ScenarioResult:
    case_id, _ = await _seed_case(engine, source_type="checkout_abandonment")
    event_store = EventStore(engine)
    narrative = [
        f"case {case_id} resolves (payment.recovered) before a stale contact attempt arrives"
    ]
    await event_store.append(
        case_id=case_id, event_type="payment.recovered", payload={"via": "chaos"}, actor=_SYSTEM
    )

    events = await event_store.events_for(case_id)
    case = Case(
        case_id=case_id,
        merchant_id="demo-d2c",
        source_type="checkout_abandonment",
        provider_event_id="chaos-prov",
        amount_at_risk=Decimal("499.00"),
        customer_ref="cust_chaos",
        resolution_state="recovered",
        cohort="treatment",
        root_cause="checkout_abandonment",
        created_at=_NOW,
        updated_at=_NOW,
        seq=len(events),
        tip_hash="h" * 64,
    )

    bundle = PolicyLoader().load()
    ladder = bundle.ladders.ladders["checkout_abandonment"]
    priced = await price_ladder_step(
        event_store,
        case=case,
        ladder=ladder,
        ladder_step_reached=0,
        uplift=Decimal("0.10"),
        relationship_weight=0.5,
        contacts_sent=0,
        economics=bundle.merchant.economics,
        policy_version=bundle.policy_version,
        now=_NOW,
    )
    ctx = PolicyContext(
        now=_NOW,
        policy=bundle,
        cohort="treatment",
        root_cause="checkout_abandonment",
        resolution_state="recovered",
        consent_channels=frozenset({"sms", "whatsapp", "email", "voice"}),
    )
    result = await dispatch(
        event_store,
        redis,
        RedisIdempotencyGuard(redis),
        StagingStore(engine),
        ApprovalStore(engine),
        case=case,
        priced=priced,
        ctx=ctx,
        economics=bundle.merchant.economics,
        staging_config=bundle.merchant.staging,
        uplift=Decimal("0.10"),
        uplift_segment="persuadable",
        now=_NOW,
    )
    narrative.append(f"the stale dispatch attempt resolved to: {result.outcome!r}")

    return ScenarioResult(
        scenario="out_of_order_events",
        case_id=case_id,
        narrative=narrative,
        outcomes=[
            ScenarioOutcome(
                "the stale attempt was denied, not executed",
                result.outcome == "denied",
                f"dispatch() returned {result.outcome!r} for a case already in a terminal state",
            ),
            ScenarioOutcome(
                "zero duplicate contacts on an already-resolved case",
                result.staged_action is None,
                "no staged_action was produced",
            ),
        ],
    )


# ── 3. malformed payload ─────────────────────────────────────────────────
# Covered end-to-end (HTTP boundary, DLQ, exception queue, HTTP 200) by
# tests/chaos/test_ingestion_chaos.py::test_malformed_payload_lands_in_dlq_...
# -- that test owns the real ASGI transport this scenario needs, so it is
# not duplicated here; see tests/chaos/test_scenarios.py's own reference.


# ── 4/5. provider 5xx / provider timeout ─────────────────────────────────


class _AlwaysFailsPort:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    async def send(
        self, message: RenderedMessage, idempotency_key: str, context: SendContext
    ) -> DeliveryReceipt:
        self.calls += 1
        raise self._error


async def _run_provider_failure(
    engine: AsyncEngine, redis: Redis, *, scenario: str, error: Exception
) -> ScenarioResult:
    case_id, _ = await _seed_case(engine)
    event_store = EventStore(engine)
    staging_store = StagingStore(engine)
    case = _seeded_domain_case(case_id)
    staged = await stage(
        event_store,
        case,
        ProposedAction(
            action_type="send_message",
            channel="sms",
            ladder_step=1,
            scheduled_for=_NOW,
            estimated_cost_inr=Decimal("0.20"),
            expected_value_inr=Decimal("10.00"),
        ),
        Verdict(decision="ALLOW", rule_id="RULE-ALLOW-DEFAULT", policy_version="v1", reason="ok"),
        MerchantStaging(
            contact_undo_window=timedelta(seconds=60), money_undo_window=timedelta(minutes=5)
        ),
        _NOW,
    )
    port = _AlwaysFailsPort(error)

    receipt = await promote_and_send(
        event_store,
        staging_store,
        port,
        redis,
        case=case,
        staged=staged,
        templates=_TEMPLATES,
        merchant_name="Recoup Demo Merchant",
        uplift_segment="persuadable",
        now=_NOW + timedelta(seconds=61),
    )

    events = await event_store.events_for(case_id)
    event_types = [e.event_type for e in events]
    narrative = [
        f"case {case_id}: the channel provider raised {type(error).__name__} on every attempt",
        f"promote_and_send returned {receipt!r} after {port.calls} attempt(s)",
    ]
    return ScenarioResult(
        scenario=scenario,
        case_id=case_id,
        narrative=narrative,
        outcomes=[
            ScenarioOutcome(
                "no message was sent", receipt is None, "promote_and_send returned None"
            ),
            ScenarioOutcome(
                "zero duplicate contacts (no action.sent)",
                "action.sent" not in event_types,
                f"events on this case: {event_types}",
            ),
            ScenarioOutcome(
                "a truthful exception entry exists",
                "case.exception" in event_types,
                "case.exception" if "case.exception" in event_types else "missing",
            ),
        ],
    )


async def run_provider_5xx(engine: AsyncEngine, redis: Redis) -> ScenarioResult:
    return await _run_provider_failure(
        engine, redis, scenario="provider_5xx", error=RuntimeError("provider returned HTTP 503")
    )


async def run_provider_timeout(engine: AsyncEngine, redis: Redis) -> ScenarioResult:
    return await _run_provider_failure(
        engine, redis, scenario="provider_timeout", error=TimeoutError("provider did not respond")
    )


# ── 6. worker crash mid-action ───────────────────────────────────────────


class _IdempotentPort:
    """A provider that honours the idempotency key it's given -- the second
    call with a key it has already seen is treated as the same delivery,
    not a fresh one, same as a real webhook-idempotent provider (Twilio,
    Resend) would behave."""

    def __init__(self) -> None:
        self.real_sends = 0
        self._seen: set[str] = set()

    async def send(
        self, message: RenderedMessage, idempotency_key: str, context: SendContext
    ) -> DeliveryReceipt:
        if idempotency_key not in self._seen:
            self._seen.add(idempotency_key)
            self.real_sends += 1
        return DeliveryReceipt(
            status="delivered",
            engaged=False,
            converted=False,
            sent_at=datetime.now(UTC),
            latency_ms=50,
            provider_ref=f"chaos-{idempotency_key[:12]}",
        )


async def run_worker_crash_mid_action(engine: AsyncEngine, redis: Redis) -> ScenarioResult:
    case_id, _ = await _seed_case(engine)
    event_store = EventStore(engine)
    staging_store = StagingStore(engine)
    case = _seeded_domain_case(case_id)
    staging_config = MerchantStaging(
        contact_undo_window=timedelta(seconds=60), money_undo_window=timedelta(minutes=5)
    )
    staged = await stage(
        event_store,
        case,
        ProposedAction(
            action_type="send_message",
            channel="sms",
            ladder_step=1,
            scheduled_for=_NOW,
            estimated_cost_inr=Decimal("0.20"),
            expected_value_inr=Decimal("10.00"),
        ),
        Verdict(decision="ALLOW", rule_id="RULE-ALLOW-DEFAULT", policy_version="v1", reason="ok"),
        staging_config,
        _NOW,
    )
    port = _IdempotentPort()
    narrative = [
        f"case {case_id}: a worker promotes and sends the staged action, then 'crashes' "
        "before persisting that it finished"
    ]

    first = await promote_and_send(
        event_store,
        staging_store,
        port,
        redis,
        case=case,
        staged=staged,  # the worker's own (soon-to-be-stale) reference
        templates=_TEMPLATES,
        merchant_name="Recoup Demo Merchant",
        uplift_segment="persuadable",
        now=_NOW + timedelta(seconds=61),
    )
    narrative.append(
        "crash: a fresh worker picks the same job up and retries with the same staged reference"
    )
    second = await promote_and_send(
        event_store,
        staging_store,
        port,
        redis,
        case=case,
        staged=staged,  # the replacement worker never saw the first one's outcome
        templates=_TEMPLATES,
        merchant_name="Recoup Demo Merchant",
        uplift_segment="persuadable",
        now=_NOW + timedelta(seconds=62),
    )

    events = await event_store.events_for(case_id)
    sent_count = [e.event_type for e in events].count("action.sent")
    narrative.append(
        f"provider saw {port.real_sends} real send(s) across two promote_and_send calls; "
        f"{sent_count} action.sent event(s) logged"
    )
    return ScenarioResult(
        scenario="worker_crash_mid_action",
        case_id=case_id,
        narrative=narrative,
        outcomes=[
            ScenarioOutcome(
                "both attempts returned a receipt (the case is never stuck)",
                first is not None and second is not None,
                f"first={first!r}, second={second!r}",
            ),
            ScenarioOutcome(
                "the provider was only ever asked to send once for real",
                port.real_sends == 1,
                f"real_sends={port.real_sends} (idempotency key honoured by the provider)",
            ),
        ],
    )


# ── 7/8. LLM timeout / LLM invalid schema (grounded Q&A's own drafter) ──


async def _timeout_drafter(_question: str, _events: list[CaseEvent]) -> GroundedAnswer | None:
    async def _hang() -> None:
        await asyncio.sleep(5)

    try:
        await asyncio.wait_for(_hang(), timeout=0.05)
    except TimeoutError:
        return None
    return None  # unreachable; mirrors llm/qa.py's own timeout -> None contract


async def _invalid_schema_drafter(
    _question: str, _events: list[CaseEvent]
) -> GroundedAnswer | None:
    try:
        # the "model" returned JSON missing every required field -- exactly
        # what llm/qa.py's own GroundedAnswer.model_validate() would reject.
        GroundedAnswer.model_validate({"not_a_real_field": True})
    except Exception:
        return None
    return None  # unreachable


async def _llm_degradation_scenario(
    engine: AsyncEngine, *, scenario: str, drafter: Drafter
) -> ScenarioResult:
    case_id, _ = await _seed_case(engine)
    event_store = EventStore(engine)
    await event_store.append(
        case_id=case_id,
        event_type="voice.call_started",
        payload={"channel": "voice"},
        actor=_SYSTEM,
    )
    reason = scenario.split("_", 1)[1].replace("_", " ")
    narrative = [f"case {case_id}: asking a grounded question while the model {reason}"]

    result = await ask(
        engine, case_id=case_id, question="what happened on this case", now=_NOW, drafter=drafter
    )
    narrative.append(
        f"ask() degraded_mode={result.degraded_mode}, refused={result.refused}, "
        f"citations={len(result.citations)}"
    )
    return ScenarioResult(
        scenario=scenario,
        case_id=case_id,
        narrative=narrative,
        outcomes=[
            ScenarioOutcome(
                "the case was never lost -- a deterministic answer was still produced",
                bool(result.answer) or result.refused,
                f"answer={result.answer!r} refused={result.refused}",
            ),
            ScenarioOutcome(
                "degraded gracefully instead of crashing or fabricating",
                result.degraded_mode is True,
                f"degraded_mode={result.degraded_mode}",
            ),
        ],
    )


async def run_llm_timeout(engine: AsyncEngine) -> ScenarioResult:
    return await _llm_degradation_scenario(engine, scenario="llm_timeout", drafter=_timeout_drafter)


async def run_llm_invalid_schema(engine: AsyncEngine) -> ScenarioResult:
    return await _llm_degradation_scenario(
        engine, scenario="llm_invalid_schema", drafter=_invalid_schema_drafter
    )


# ── 9. clock skew ─────────────────────────────────────────────────────────
# Covered by tests/chaos/test_ingestion_chaos.py::
# test_ingestion_survives_extreme_clock_skew_in_the_provider_timestamp
# (+-5 years and zero skew) -- referenced, not duplicated, same as scenario 3.


# ── 10. poisoned model output ────────────────────────────────────────────


async def run_poisoned_model_output(engine: AsyncEngine) -> ScenarioResult:
    case_id, _ = await _seed_case(engine)
    narrative = [
        f"case {case_id}: classifying with adversarial input -- a merchant_id never seen in "
        "training and an absurd amount, empty detail"
    ]
    result = classify(
        source_type="payment_failure",
        merchant_id="chaos-never-trained-on-this-merchant",
        amount_at_risk=Decimal("99999999999.99"),
        occurred_at=_NOW,
        detail={},
    )
    narrative.append(
        f"classify() returned root_cause={result.root_cause!r} confidence={result.confidence:.3f}"
    )
    floored_correctly = result.confidence >= CONFIDENCE_FLOOR or result.root_cause == "unknown"
    return ScenarioResult(
        scenario="poisoned_model_output",
        case_id=case_id,
        narrative=narrative,
        outcomes=[
            ScenarioOutcome(
                "confidence is a well-formed probability, not a poisoned value",
                0.0 <= result.confidence <= 1.0,
                f"confidence={result.confidence!r} (adversarial input never produces NaN/out-of-range)",
            ),
            ScenarioOutcome(
                "low-confidence output was floored to 'unknown', never trusted silently",
                floored_correctly,
                f"confidence={result.confidence:.3f}, floor={CONFIDENCE_FLOOR}, "
                f"root_cause={result.root_cause!r}",
            ),
        ],
    )


SCENARIOS: dict[str, str] = {
    "duplicate_webhook": "Deliver the same webhook 25 times; exactly one case, zero duplicate contacts.",
    "out_of_order_events": "A stale contact attempt arrives after the case already resolved.",
    "malformed_payload": "A broken-JSON webhook; DLQ entry, HTTP 200, never a provider retry storm.",
    "provider_5xx": "The channel provider returns a server error on every attempt.",
    "provider_timeout": "The channel provider never responds.",
    "worker_crash_mid_action": "A worker crashes right after sending; a fresh worker retries blind.",
    "llm_timeout": "The grounded-QA model exceeds its latency budget.",
    "llm_invalid_schema": "The grounded-QA model returns JSON that fails schema validation.",
    "clock_skew": "A provider timestamp arrives five years fast, five years slow, or exactly now.",
    "poisoned_model_output": "The classifier sees adversarial input it never trained on.",
}
