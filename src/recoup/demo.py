"""`make demo`'s orchestration (FR-13, end to end): generate a seeded batch,
ingest it through the real pipeline, assign cohorts before any scoring,
score every case (classify + uplift -- a pure analysis step, not a contact,
so it is safe to run on control cases too and is exactly where the CUPED
covariate `p_recover_baseline` comes from), walk every *treatment* case
through its full recovery ladder against the real policy/economics/
execution pipeline, and decide each case's resolution from the generator's
own hidden ground truth -- never a model-visible feature (see
`data/generate.py`, `data/simulate.py`).

A denial (quiet hours, opt-out, fatigue cap, ...) ends a case's ladder walk
rather than skipping ahead to the next step: `policy.evaluate`'s
RULE-LADDER-SEQUENCE requires each step to follow the one actually
completed before it, so a denied step cannot be skipped past -- the case
simply carries whatever contacts it already made into the final ground-truth
resolution roll, same as an exhausted or abandoned ladder.

`case.measurement_resolved` is a *separate* event type from `payment.
recovered` (which `promote_and_send`'s own simulator can still append on its
own `engaged`/`converted` signal): the channel simulator's conversion flag
has nothing to say about what a *control* case would have done, so it
cannot be the arm-comparable signal the headline number is built from. The
ground-truth roll here is authoritative for measurement; the channel
simulator's own signal is a separate, illustrative artifact of the
message-delivery pipeline.

Every per-case phase (ingest, cohort recording, scoring, ladder walk,
resolution roll) is independent case-to-case, so each runs under a bounded
`asyncio.gather` rather than a sequential loop -- with ~500 cases each
touching Postgres and Redis several times, sequential awaits alone made a
full batch take minutes; nothing about correctness depends on the order
cases are processed in, since every random draw is seeded from the case's
own id, not from call order.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from recoup.audit.event_store import EventStore, create_engine
from recoup.audit.projection import project
from recoup.audit.verify import verify_chain, verify_replay_equality
from recoup.data.generate import generate_batch
from recoup.data.simulate import resolution_probability, simulate_resolved
from recoup.domain.ids import deterministic_ulid
from recoup.domain.models import Actor, Cohort
from recoup.economics.ev import price_ladder_step
from recoup.execution.adapters.simulator import SimulatorChannelPort
from recoup.execution.approvals import ApprovalStore
from recoup.execution.dispatcher import dispatch, promote_and_send
from recoup.execution.idempotency import RedisIdempotencyGuard
from recoup.execution.staging import StagingStore
from recoup.execution.templates import TemplateLoader, TemplateSet
from recoup.ingestion.ingest import ingest
from recoup.ingestion.models import NormalizedIntake
from recoup.measurement.cohort import (
    CaseForAssignment,
    CohortAssignment,
    Stratum,
    assign_cohorts,
    record_assignment,
)
from recoup.measurement.report import BatchInputs, BreakdownRow, HeadlineReport, build_report
from recoup.measurement.stats import two_proportion_z_test
from recoup.policy.categories import category_for
from recoup.policy.context import PolicyContext
from recoup.policy.loader import PolicyLoader
from recoup.policy.schema import PolicyBundle
from recoup.settings import get_settings
from recoup.understanding.score import score_case

_BATCH_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)  # a Friday, within permitted contact hours
_MERCHANT_NAME = "Recoup Demo Merchant"
_ALL_CHANNELS = frozenset({"sms", "whatsapp", "email", "voice"})
_SYSTEM = Actor(kind="system", identifier="measurement.simulate")
_CONCURRENCY = 15  # matches create_engine()'s default pool_size(5) + max_overflow(10)


async def _gather_bounded[T](
    coros: Iterable[Awaitable[T]], *, limit: int = _CONCURRENCY
) -> list[T]:
    semaphore = asyncio.Semaphore(limit)

    async def _run(coro: Awaitable[T]) -> T:
        async with semaphore:
            return await coro

    return await asyncio.gather(*(_run(c) for c in coros))


@dataclass
class _CaseLedger:
    case_id: str
    cohort: Cohort
    excluded_from_control: bool
    root_cause: str
    amount_at_risk: Decimal
    baseline_propensity: float
    uplift: Decimal
    relationship_weight: float
    uplift_segment: str | None
    stratum: Stratum
    contacts_sent: int = 0
    spend_inr: Decimal = Decimal("0")
    last_channel: str | None = None
    avoided_cost_inr: Decimal = Decimal("0")
    resolved: bool = False


async def _walk_treatment_case(
    event_store: EventStore,
    redis: Redis,
    idempotency_guard: RedisIdempotencyGuard,
    staging_store: StagingStore,
    approval_store: ApprovalStore,
    templates: TemplateSet,
    *,
    ledger: _CaseLedger,
    bundle: PolicyBundle,
    seed: int,
) -> None:
    ladder = bundle.ladders.ladders.get(ledger.root_cause) or bundle.ladders.ladders["unknown"]
    events = await event_store.events_for(ledger.case_id)
    case = project(events)

    clock = _BATCH_NOW
    for step_index in range(len(ladder.steps)):
        if step_index > 0:
            clock = clock + ladder.steps[step_index].wait_before

        priced = await price_ladder_step(
            event_store,
            case=case,
            ladder=ladder,
            ladder_step_reached=step_index,
            uplift=ledger.uplift,
            relationship_weight=ledger.relationship_weight,
            contacts_sent=ledger.contacts_sent,
            economics=bundle.merchant.economics,
            policy_version=bundle.policy_version,
            now=clock,
        )
        if not priced:
            break

        ctx = PolicyContext(
            now=clock,
            policy=bundle,
            cohort="treatment",
            root_cause=ledger.root_cause,
            resolution_state="pending",
            ladder_step_reached=step_index,
            consent_channels=_ALL_CHANNELS,
            contacts_sent=ledger.contacts_sent,
        )
        result = await dispatch(
            event_store,
            redis,
            idempotency_guard,
            staging_store,
            approval_store,
            case=case,
            priced=priced,
            ctx=ctx,
            economics=bundle.merchant.economics,
            staging_config=bundle.merchant.staging,
            uplift=ledger.uplift,
            uplift_segment=ledger.uplift_segment,
            now=clock,
            rng=random.Random(f"{seed}:{ledger.case_id}:{step_index}"),
        )

        if result.outcome == "abandoned":
            ledger.avoided_cost_inr = max(
                (c.action.estimated_cost_inr for c in priced), default=Decimal("0")
            )
            break
        if result.outcome != "staged":
            # denied / exhausted / require_approval / duplicate_suppressed all end
            # this case's walk -- a denial cannot be skipped past (RULE-LADDER-
            # SEQUENCE requires each step to follow the one actually completed).
            break

        staged = result.staged_action
        assert staged is not None
        if staged.channel is None:
            # retry_charge / stop / anything non-channel: not executable in this
            # build (agent-initiated Razorpay retry doesn't exist yet -- see
            # dispatcher.py's own module docstring). Logged as staged; try the
            # next escalation step.
            clock = staged.promote_at
            continue

        receipt = await promote_and_send(
            event_store,
            staging_store,
            SimulatorChannelPort(),
            redis,
            case=case,
            staged=staged,
            templates=templates,
            merchant_name=_MERCHANT_NAME,
            uplift_segment=ledger.uplift_segment,
            now=staged.promote_at,
        )
        clock = staged.promote_at
        if receipt is not None and receipt.status == "delivered":
            ledger.contacts_sent += 1
            ledger.spend_inr += staged.estimated_cost_inr
            ledger.last_channel = staged.channel
            if receipt.engaged:
                break  # customer responded; stop escalating


async def _tally_blocked_and_exceptions(
    event_store: EventStore, case_ids: list[str]
) -> tuple[dict[str, int], int]:
    all_events = await _gather_bounded(event_store.events_for(case_id) for case_id in case_ids)
    blocked: dict[str, int] = {}
    exception_count = 0
    for events in all_events:
        for event in events:
            if event.event_type == "policy.denied":
                category = category_for(str(event.payload.get("rule_id", "")))
                blocked[category] = blocked.get(category, 0) + 1
            elif event.event_type == "case.exception":
                exception_count += 1
    return blocked, exception_count


def _build_breakdowns(treated: list[_CaseLedger], control: list[_CaseLedger]) -> list[BreakdownRow]:
    rows: list[BreakdownRow] = []
    dimensions: tuple[tuple[str, Callable[[_CaseLedger], str]], ...] = (
        ("root_cause", lambda ledger: ledger.root_cause),
        ("segment", lambda ledger: ledger.uplift_segment or "unscored"),
        ("value_band", lambda ledger: ledger.stratum.amount_band),
        ("channel", lambda ledger: ledger.last_channel or "none"),
    )
    for dimension, key_fn in dimensions:
        keys = {key_fn(lg) for lg in treated} | {key_fn(lg) for lg in control}
        for key in sorted(keys):
            t_group = [lg for lg in treated if key_fn(lg) == key]
            c_group = [lg for lg in control if key_fn(lg) == key]
            if not t_group or not c_group:
                continue
            result = two_proportion_z_test(
                n_treated=len(t_group),
                x_treated=sum(1 for lg in t_group if lg.resolved),
                n_control=len(c_group),
                x_control=sum(1 for lg in c_group if lg.resolved),
            )
            rows.append(BreakdownRow(dimension=dimension, key=key, result=result))
    return rows


async def run_batch(
    *, seed: int = 42, n_cases: int = 500, batch_id: str | None = None
) -> HeadlineReport:
    settings = get_settings()
    engine = create_engine()
    redis = Redis.from_url(settings.redis_url)
    resolved_batch_id = batch_id or f"b_seed{seed}_{n_cases}"
    try:
        bundle = PolicyLoader().load()
        templates = TemplateLoader().load()
        gen_batch = generate_batch(seed=seed, n_cases=n_cases)
        ground_truth_by_provider_id = {g.provider_event_id: g for g in gen_batch.ground_truth}

        event_store = EventStore(engine)
        staging_store = StagingStore(engine)
        approval_store = ApprovalStore(engine)
        idempotency_guard = RedisIdempotencyGuard(redis)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async def _ingest_one(intake: NormalizedIntake) -> str:
            # A fixed seed must reproduce identical case IDs -- every
            # downstream per-case RNG draw is keyed on the case id, so a
            # `new_ulid()`-minted (wall-clock + OS entropy) id here would
            # silently launder non-determinism into a "seeded" batch.
            deterministic_case_id = deterministic_ulid(f"case:{seed}:{intake.provider_event_id}")
            async with session_factory() as session:
                ingest_result = await ingest(
                    session, event_store, intake, case_id_override=deterministic_case_id
                )
            return ingest_result.case_id

        case_ids = await _gather_bounded([_ingest_one(intake) for intake in gen_batch.intake])
        provider_id_by_case = {
            case_id: intake.provider_event_id
            for case_id, intake in zip(case_ids, gen_batch.intake, strict=True)
        }
        amount_by_case = {
            case_id: intake.amount_at_risk
            for case_id, intake in zip(case_ids, gen_batch.intake, strict=True)
        }

        assignment_inputs = [
            CaseForAssignment(
                case_id=case_id,
                source_type=intake.source_type,
                amount_at_risk=intake.amount_at_risk,
                merchant_id=intake.merchant_id,
                error_reason=intake.detail.get("error_reason"),
            )
            for case_id, intake in zip(case_ids, gen_batch.intake, strict=True)
        ]
        measurement_config = bundle.merchant.measurement
        assignments = assign_cohorts(
            assignment_inputs,
            holdout_rate=measurement_config.default_holdout_rate,
            value_cap_inr=measurement_config.value_cap_inr,
            salt=measurement_config.salt,
        )
        await _gather_bounded(
            record_assignment(event_store, assignment, policy_version=bundle.policy_version)
            for assignment in assignments
        )

        await _gather_bounded(score_case(event_store, case_id) for case_id in case_ids)

        async def _build_ledger(assignment: CohortAssignment) -> _CaseLedger:
            events = await event_store.events_for(assignment.case_id)
            scored = next(e for e in events if e.event_type == "case.scored")
            classified = next(e for e in events if e.event_type == "case.classified")
            return _CaseLedger(
                case_id=assignment.case_id,
                cohort=assignment.cohort,
                excluded_from_control=assignment.excluded_from_control,
                root_cause=str(classified.payload["root_cause"]),
                amount_at_risk=amount_by_case[assignment.case_id],
                baseline_propensity=float(scored.payload["p_recover_baseline"]),
                uplift=Decimal(str(scored.payload["uplift"])),
                relationship_weight=float(scored.payload["relationship_weight"]),
                uplift_segment=scored.payload["uplift_segment"],
                stratum=assignment.stratum,
            )

        ledger_list = await _gather_bounded(_build_ledger(a) for a in assignments)
        ledgers: dict[str, _CaseLedger] = {lg.case_id: lg for lg in ledger_list}

        await _gather_bounded(
            _walk_treatment_case(
                event_store,
                redis,
                idempotency_guard,
                staging_store,
                approval_store,
                templates,
                ledger=ledgers[assignment.case_id],
                bundle=bundle,
                seed=seed,
            )
            for assignment in assignments
            if assignment.cohort == "treatment"
        )

        async def _resolve_one(case_id: str, ledger: _CaseLedger) -> None:
            ground_truth = ground_truth_by_provider_id[provider_id_by_case[case_id]]
            channel = ledger.last_channel if ledger.cohort == "treatment" else None
            probability = resolution_probability(ground_truth, channel)
            resolved = simulate_resolved(case_id=case_id, seed=seed, probability=probability)
            ledger.resolved = resolved
            await event_store.append(
                case_id=case_id,
                event_type="case.measurement_resolved",
                payload={"resolved": resolved, "channel": channel, "cohort": ledger.cohort},
                actor=_SYSTEM,
                policy_version=bundle.policy_version,
            )

        await _gather_bounded(_resolve_one(case_id, ledger) for case_id, ledger in ledgers.items())

        treated = [lg for lg in ledgers.values() if lg.cohort == "treatment"]
        control = [lg for lg in ledgers.values() if lg.cohort == "control"]

        at_risk_inr = sum((lg.amount_at_risk for lg in ledgers.values()), Decimal("0"))
        raw_recovered_inr = sum((lg.amount_at_risk for lg in treated if lg.resolved), Decimal("0"))
        x_treated = sum(1 for lg in treated if lg.resolved)
        x_control = sum(1 for lg in control if lg.resolved)
        mean_recovered_value_inr = (raw_recovered_inr / x_treated) if x_treated else Decimal("0")

        max_touches = bundle.regulatory.contact_fatigue.max_contacts
        max_touches_respected_rate = (
            sum(1 for lg in treated if lg.contacts_sent <= max_touches) / len(treated)
            if treated
            else 1.0
        )

        blocked_by_policy, exception_count = await _tally_blocked_and_exceptions(
            event_store, list(ledgers.keys())
        )
        chain = await verify_chain(engine)
        replay_ok = await verify_replay_equality(engine) if chain.verified else False

        exclusions: dict[str, int] = {}
        for ledger in ledgers.values():
            if ledger.excluded_from_control:
                exclusions["value_cap_or_legal_risk"] = (
                    exclusions.get("value_cap_or_legal_risk", 0) + 1
                )

        inputs = BatchInputs(
            batch_id=resolved_batch_id,
            seed=seed,
            n_cases_total=len(ledgers),
            at_risk_inr=at_risk_inr,
            raw_recovered_inr=raw_recovered_inr,
            n_treated=len(treated),
            x_treated=x_treated,
            n_control=len(control),
            x_control=x_control,
            mean_recovered_value_inr=mean_recovered_value_inr,
            treated_outcomes=[1.0 if lg.resolved else 0.0 for lg in treated],
            treated_covariates=[lg.baseline_propensity for lg in treated],
            control_outcomes=[1.0 if lg.resolved else 0.0 for lg in control],
            control_covariates=[lg.baseline_propensity for lg in control],
            spend_on_contact_inr=sum((lg.spend_inr for lg in treated), Decimal("0")),
            saved_by_not_contacting_inr=sum((lg.avoided_cost_inr for lg in treated), Decimal("0")),
            actions_blocked_by_policy=blocked_by_policy,
            contacts_per_resolved_case=[lg.contacts_sent for lg in treated if lg.resolved],
            max_touches_respected_rate=max_touches_respected_rate,
            cases_in_exception_queue=exception_count,
            exception_queue_all_triaged=True,
            audit_chain_verified=chain.verified,
            replay_equality_passed=replay_ok,
            breakdowns=_build_breakdowns(treated, control),
            exclusions=exclusions,
        )
        return build_report(inputs)
    finally:
        await engine.dispose()
        await redis.aclose()
