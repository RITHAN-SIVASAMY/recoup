"""The policy engine. Pure. Sync. No I/O, no LLM, no clock access.

`evaluate()` never queries the database, the clock, or an LLM — `ctx` carries
everything, including `now`, so this function is fully deterministic and
property-testable. Evaluation order is fixed and short-circuiting (see
docs/03-ARCHITECTURE.md §7): kill switch/exposure -> cohort -> idempotency ->
regulatory -> hard stopping rules -> contact-fatigue budget -> ladder validity
-> approval thresholds -> ALLOW. The first rule that fires wins; nothing after
it is evaluated.
"""

from __future__ import annotations

from recoup.domain.idempotency import idempotency_key
from recoup.domain.models import Case, ProposedAction, Verdict
from recoup.policy.context import PolicyContext
from recoup.policy.rules.consent import has_consent
from recoup.policy.rules.mandate import (
    exceeds_cadence_cap,
    is_never_retry_cause,
    requires_additional_authentication,
    requires_pre_debit_notice,
    violates_minimum_gap,
)
from recoup.policy.rules.opt_out import blocks_contact
from recoup.policy.rules.quiet_hours import is_within_permitted_hours

_TERMINAL_STATES = {
    "recovered",
    "stopped_by_policy",
    "abandoned_uneconomic",
    "control_untouched",
}


def _verdict(
    ctx: PolicyContext,
    decision: str,
    rule_id: str,
    reason: str,
    obligations: list[str] | None = None,
) -> Verdict:
    return Verdict(
        decision=decision,  # type: ignore[arg-type]
        rule_id=rule_id,
        policy_version=ctx.policy.policy_version,
        reason=reason,
        obligations=obligations or [],
    )


def evaluate(case: Case, action: ProposedAction, ctx: PolicyContext) -> Verdict:
    reg = ctx.policy.regulatory
    is_contact = action.channel is not None

    # 1. Kill switch / exposure cap
    if ctx.kill_switch_engaged:
        return _verdict(ctx, "DENY", "RULE-KILL-001", "Global kill switch is engaged.")
    if ctx.exposure_used_inr + action.estimated_cost_inr > ctx.policy.merchant.exposure_cap_inr:
        return _verdict(
            ctx,
            "REQUIRE_APPROVAL",
            "RULE-EXPOSURE-001",
            "Merchant exposure cap would be exceeded; queued for approval instead of auto-executed.",
        )

    # 2. Cohort — control cases receive zero actions, ever.
    if ctx.cohort == "control":
        return _verdict(ctx, "DENY", "RULE-CTRL-001", "Case is in the control cohort.")

    # Idempotency (defense in depth alongside the DB-level guarantee in EventStore).
    key = idempotency_key(
        case.case_id, action.action_type, action.ladder_step, ctx.policy.policy_version
    )
    if key in ctx.already_executed_idempotency_keys:
        return _verdict(
            ctx, "DENY", "RULE-DUP-001", "This exact action already executed (idempotency key)."
        )

    # 3. Regulatory
    if is_contact and blocks_contact(ctx.opted_out):
        return _verdict(
            ctx, "DENY", "REG-COMM-03", "Customer has opted out; honoured across all cases."
        )
    if is_contact and not has_consent(action.channel, ctx.consent_channels):
        return _verdict(
            ctx, "DENY", "REG-COMM-02", f"No recorded consent for channel {action.channel!r}."
        )
    if is_contact and not is_within_permitted_hours(ctx.now, reg.quiet_hours):
        return _verdict(
            ctx,
            "DENY",
            "REG-COMM-01",
            f"Outside permitted contact hours ({reg.quiet_hours.start}-{reg.quiet_hours.end} {reg.quiet_hours.tz}).",
        )
    if action.action_type == "retry_charge" and is_never_retry_cause(
        ctx.root_cause, reg.mandate_retry.never_retry_causes
    ):
        return _verdict(
            ctx,
            "DENY",
            "REG-MAND-01",
            f"{ctx.root_cause} is never silently retried; re-authorize instead.",
        )
    if action.action_type == "retry_charge" and requires_additional_authentication(
        action.expected_value_inr, reg.mandate_retry.afa_threshold_inr
    ):
        return _verdict(
            ctx,
            "DENY",
            "REG-MAND-04",
            "Value is above the AFA threshold; needs a re-authorization link, not an automated retry.",
        )
    if action.action_type == "retry_charge" and ctx.root_cause == "mandate_technical_failure":
        if exceeds_cadence_cap(ctx.retry_charge_attempts, reg.mandate_retry.max_per_cycle):
            return _verdict(
                ctx, "DENY", "REG-MAND-02", "Mandate retry cadence cap reached for this cycle."
            )
        if violates_minimum_gap(ctx.last_retry_charge_at, ctx.now, reg.mandate_retry.min_gap):
            return _verdict(
                ctx, "DENY", "REG-MAND-02", "Minimum gap between mandate retries not yet elapsed."
            )
        if requires_pre_debit_notice(
            required=reg.mandate_retry.pre_debit_notice_required,
            already_sent=ctx.pre_debit_notice_sent,
        ):
            return _verdict(
                ctx,
                "DENY",
                "REG-MAND-03",
                "Pre-debit notice must be sent before this retry is proposed.",
            )

    # 4. Hard stopping rules
    if case.resolution_state in _TERMINAL_STATES:
        return _verdict(
            ctx,
            "DENY",
            "RULE-STOP-TERMINAL",
            f"Case is already in a terminal state: {case.resolution_state}.",
        )

    # 5. Contact-fatigue budget (REG-COMM-06 — rolling, per customer, across all cases)
    if is_contact and ctx.contacts_sent >= reg.contact_fatigue.max_contacts:
        return _verdict(
            ctx,
            "DENY",
            "REG-COMM-06",
            f"Contact-fatigue budget exhausted ({reg.contact_fatigue.max_contacts} per {reg.contact_fatigue.window}).",
        )

    # 6. Ladder validity
    ladder = (
        ctx.policy.ladders.ladders.get(ctx.root_cause or "unknown")
        or ctx.policy.ladders.ladders["unknown"]
    )
    if action.action_type in ladder.forbidden_actions:
        return _verdict(
            ctx,
            "DENY",
            "RULE-LADDER-FORBIDDEN",
            f"{action.action_type} is forbidden for {ctx.root_cause}.",
        )
    step_index = action.ladder_step - 1
    if step_index < 0 or step_index >= len(ladder.steps):
        return _verdict(
            ctx, "DENY", "RULE-LADDER-SEQUENCE", "ladder_step is out of range for this ladder."
        )
    expected_step = ladder.steps[step_index]
    if expected_step.action != action.action_type:
        return _verdict(
            ctx,
            "DENY",
            "RULE-LADDER-SEQUENCE",
            f"Step {action.ladder_step} of this ladder is {expected_step.action}, not {action.action_type}.",
        )
    if action.ladder_step != ctx.ladder_step_reached + 1:
        return _verdict(
            ctx,
            "DENY",
            "RULE-LADDER-SEQUENCE",
            f"Case has reached step {ctx.ladder_step_reached}; step {action.ladder_step} is not next.",
        )
    if (
        action.channel is not None
        and expected_step.channels is not None
        and action.channel not in expected_step.channels
    ):
        return _verdict(
            ctx,
            "DENY",
            "RULE-LADDER-CHANNEL",
            f"{action.channel} is not a permitted channel for this step.",
        )

    # 7. Approval thresholds
    if action.action_type in ctx.policy.merchant.approval.always_require:
        return _verdict(
            ctx,
            "REQUIRE_APPROVAL",
            "RULE-APPROVAL-ALWAYS",
            f"{action.action_type} always requires approval.",
        )
    if action.expected_value_inr >= ctx.policy.merchant.approval.value_threshold_inr:
        return _verdict(
            ctx,
            "REQUIRE_APPROVAL",
            "RULE-APPROVAL-VALUE",
            f"Expected value {action.expected_value_inr} is at or above the approval threshold.",
        )
    if ctx.is_flagged_account:
        return _verdict(
            ctx, "REQUIRE_APPROVAL", "RULE-APPROVAL-FLAGGED", "Account is flagged for human review."
        )

    # 8. ALLOW
    obligations = ["stage_for_60s"] if is_contact else []
    return _verdict(ctx, "ALLOW", "RULE-ALLOW-DEFAULT", "No blocking rule matched.", obligations)
