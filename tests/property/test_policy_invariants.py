"""The six system-wide invariants from docs/03-ARCHITECTURE.md §7 and FR-5.5,
asserted with Hypothesis over randomly generated cases, actions and contexts —
these make a violation *impossible*, not merely untested, which is the whole
point of policy-as-code over `if attempts > 3: stop` scattered in a service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recoup.domain.idempotency import idempotency_key
from recoup.domain.ids import new_ulid
from recoup.domain.models import Case, ProposedAction, Verdict
from recoup.policy.context import PolicyContext
from recoup.policy.evaluator import evaluate
from recoup.policy.loader import PolicyLoader

pytestmark = pytest.mark.property

_BUNDLE = PolicyLoader().load()

_ROOT_CAUSES = [
    "bank_soft_decline",
    "insufficient_funds",
    "otp_timeout_or_auth_abandon",
    "network_or_gateway_error",
    "issuer_risk_block",
    "card_expired_or_invalid",
    "mandate_revoked",
    "mandate_insufficient_balance",
    "mandate_technical_failure",
    "checkout_abandonment",
    "receivable_overdue",
    "unknown",
]
_ACTION_TYPES = [
    "retry_charge",
    "send_message",
    "send_reauth_link",
    "send_pre_debit_notice",
    "voice_call",
    "draft_formal_notice",
    "stop",
]
_CHANNELS = ["sms", "whatsapp", "email", "voice"]
_RESOLUTION_STATES = [
    "recovered",
    "pending",
    "awaiting_promise",
    "stopped_by_policy",
    "abandoned_uneconomic",
    "exception",
    "control_untouched",
]

_cases = st.builds(
    Case,
    case_id=st.just(new_ulid()),
    merchant_id=st.just("demo"),
    source_type=st.sampled_from(
        ["payment_failure", "checkout_abandonment", "mandate_failure", "receivable_overdue"]
    ),
    provider_event_id=st.just("prov-1"),
    amount_at_risk=st.decimals(min_value="1", max_value="100000", places=2).map(Decimal),
    customer_ref=st.just("cust-1"),
    resolution_state=st.sampled_from(_RESOLUTION_STATES),
    cohort=st.sampled_from(["treatment", "control", None]),
    root_cause=st.sampled_from([*_ROOT_CAUSES, None]),
    created_at=st.just(datetime(2026, 1, 1, tzinfo=UTC)),
    updated_at=st.just(datetime(2026, 1, 1, tzinfo=UTC)),
    seq=st.integers(min_value=1, max_value=50),
    tip_hash=st.just("h" * 64),
)

_actions = st.builds(
    ProposedAction,
    action_type=st.sampled_from(_ACTION_TYPES),
    channel=st.sampled_from([*_CHANNELS, None]),
    ladder_step=st.integers(min_value=1, max_value=5),
    scheduled_for=st.just(datetime(2026, 1, 2, 12, 0, tzinfo=UTC)),
    estimated_cost_inr=st.decimals(min_value="0", max_value="50", places=2).map(Decimal),
    expected_value_inr=st.decimals(min_value="0", max_value="20000", places=2).map(Decimal),
)


def _context(
    *,
    cohort: str | None,
    root_cause: str | None,
    resolution_state: str,
    now: datetime = datetime(2026, 1, 2, 12, 0, tzinfo=UTC),  # a Friday, within business hours
    opted_out: bool = False,
    consent_channels: frozenset[str] = frozenset({"sms", "whatsapp", "email", "voice"}),
    contacts_sent: int = 0,
    already_executed_idempotency_keys: frozenset[str] = frozenset(),
    kill_switch_engaged: bool = False,
) -> PolicyContext:
    return PolicyContext(
        now=now,
        policy=_BUNDLE,
        cohort=cohort,  # type: ignore[arg-type]
        root_cause=root_cause,
        resolution_state=resolution_state,  # type: ignore[arg-type]
        opted_out=opted_out,
        consent_channels=consent_channels,
        contacts_sent=contacts_sent,
        already_executed_idempotency_keys=already_executed_idempotency_keys,
        kill_switch_engaged=kill_switch_engaged,
    )


# ── 1. contacts ≤ max_contacts, always ──────────────────────────────────────
@given(case=_cases, action=_actions)
def test_never_allows_a_contact_once_the_fatigue_budget_is_exhausted(
    case: Case, action: ProposedAction
) -> None:
    ctx = _context(
        cohort="treatment",
        root_cause=case.root_cause,
        resolution_state="pending",
        contacts_sent=_BUNDLE.regulatory.contact_fatigue.max_contacts,
    )
    verdict = evaluate(case, action, ctx)
    if action.channel is not None:
        assert verdict.decision != "ALLOW"


# ── 2. no contact after opt-out, ever ───────────────────────────────────────
@given(case=_cases, action=_actions)
def test_never_allows_a_contact_after_opt_out(case: Case, action: ProposedAction) -> None:
    ctx = _context(
        cohort="treatment", root_cause=case.root_cause, resolution_state="pending", opted_out=True
    )
    verdict = evaluate(case, action, ctx)
    if action.channel is not None:
        assert verdict.decision != "ALLOW"


# ── 3. control cohort ⇒ zero actions ────────────────────────────────────────
@given(case=_cases, action=_actions)
def test_control_cohort_never_gets_any_action(case: Case, action: ProposedAction) -> None:
    ctx = _context(cohort="control", root_cause=case.root_cause, resolution_state="pending")
    verdict = evaluate(case, action, ctx)
    assert verdict.decision == "DENY"
    assert verdict.rule_id == "RULE-CTRL-001"


# ── 4. mandate_revoked / mandate_insufficient_balance ⇒ retry_charge never appears ──
@given(
    case=_cases,
    root_cause=st.sampled_from(["mandate_revoked", "mandate_insufficient_balance"]),
    action=_actions,
)
def test_never_retry_cause_never_allows_retry_charge(
    case: Case, root_cause: str, action: ProposedAction
) -> None:
    retry_action = action.model_copy(update={"action_type": "retry_charge"})
    ctx = _context(cohort="treatment", root_cause=root_cause, resolution_state="pending")
    verdict = evaluate(case, retry_action, ctx)
    assert verdict.decision != "ALLOW"
    assert verdict.rule_id == "REG-MAND-01"


# ── 5. one idempotency key ⇒ at most one executed action ───────────────────
@given(case=_cases, action=_actions)
def test_a_duplicate_idempotency_key_is_never_allowed_twice(
    case: Case, action: ProposedAction
) -> None:
    key = idempotency_key(
        case.case_id, action.action_type, action.ladder_step, _BUNDLE.policy_version
    )
    ctx = _context(
        cohort="treatment",
        root_cause=case.root_cause,
        resolution_state="pending",
        already_executed_idempotency_keys=frozenset({key}),
    )
    verdict = evaluate(case, action, ctx)
    assert verdict.decision != "ALLOW"
    assert verdict.rule_id == "RULE-DUP-001"


# ── 6. every executed action has a preceding logged ALLOW/APPROVED verdict ──
# `evaluate()` is total (never raises, always returns a well-formed Verdict) and
# ALLOW is the *only* decision this phase treats as "executable" — there is no
# code path that produces an execution signal without going through this
# function and getting a real Verdict back. Execution actually honouring that
# contract is proven later, once execution/dispatcher.py exists (GOV-MONEY-01
# in docs/06-COMPLIANCE-MATRIX.md) — this is the phase-04-scoped half.
@given(case=_cases, action=_actions, cohort=st.sampled_from(["treatment", "control"]))
def test_evaluate_always_returns_a_well_formed_verdict(
    case: Case, action: ProposedAction, cohort: str
) -> None:
    ctx = _context(
        cohort=cohort, root_cause=case.root_cause, resolution_state=case.resolution_state
    )
    verdict = evaluate(case, action, ctx)

    assert isinstance(verdict, Verdict)
    assert verdict.decision in ("ALLOW", "DENY", "REQUIRE_APPROVAL")
    assert verdict.rule_id  # never empty — every decision names the rule that produced it
    assert verdict.policy_version == _BUNDLE.policy_version
    # Verdict is frozen and only ever constructed inside evaluate() — there is no
    # other way for this codebase to produce one, which is what makes "executed
    # implies a logged verdict" true by construction rather than by convention.


# ── Kill switch: nothing gets through while it's engaged ────────────────────
@given(case=_cases, action=_actions)
def test_kill_switch_denies_everything(case: Case, action: ProposedAction) -> None:
    ctx = _context(
        cohort="treatment",
        root_cause=case.root_cause,
        resolution_state="pending",
        kill_switch_engaged=True,
    )
    verdict = evaluate(case, action, ctx)
    assert verdict.decision == "DENY"
    assert verdict.rule_id == "RULE-KILL-001"
