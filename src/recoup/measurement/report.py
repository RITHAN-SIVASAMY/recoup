"""FR-13.6/13.9/13.10: the headline block, exactly as specified in
`docs/05-EVALUATION-PROTOCOL.md` §9, assembled from already-aggregated batch
inputs and rendered as text, JSON, and Markdown.

This module does no I/O and knows nothing about `case_events`, Postgres, or
how a batch was actually run -- it is handed a `BatchInputs` record (raw
counts and per-case outcome/covariate lists) and turns it into a
`HeadlineReport`. Assembling those inputs from a real batch (querying the
event log, running the cohort/holdout/scoring pipeline end to end) is the
next phase's job; this module is what that pipeline hands its numbers to.

Rule 9's guardrail is enforced here, not upstream: `render_headline_block`
always prints the two-proportion result's raw `p_value` and the MDE, and
appends an explicit "NOT SIGNIFICANT" marker whenever `significant` is
False -- there is no formatting path that can make a null look like a win,
and no caller-supplied flag can suppress the marker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from recoup.measurement.cuped import CupedResult, cuped_adjust
from recoup.measurement.stats import TwoProportionResult, two_proportion_z_test

_RULE = "─" * 66
_DOUBLE_RULE = "═" * 66


@dataclass(frozen=True)
class BreakdownRow:
    dimension: str  # "root_cause" | "channel" | "segment" | "value_band"
    key: str
    result: TwoProportionResult


@dataclass(frozen=True)
class BatchInputs:
    batch_id: str
    seed: int
    n_cases_total: int
    at_risk_inr: Decimal
    raw_recovered_inr: Decimal
    n_treated: int
    x_treated: int
    n_control: int
    x_control: int
    mean_recovered_value_inr: Decimal
    treated_outcomes: list[float]
    treated_covariates: list[float]
    control_outcomes: list[float]
    control_covariates: list[float]
    spend_on_contact_inr: Decimal
    saved_by_not_contacting_inr: Decimal
    actions_blocked_by_policy: dict[str, int]
    contacts_per_resolved_case: list[int]
    max_touches_respected_rate: float
    cases_in_exception_queue: int
    exception_queue_all_triaged: bool
    audit_chain_verified: bool
    replay_equality_passed: bool
    breakdowns: list[BreakdownRow] = field(default_factory=list)
    exclusions: dict[str, int] = field(default_factory=dict)  # exclusion_reason-ish -> count


@dataclass(frozen=True)
class HeadlineReport:
    inputs: BatchInputs
    significance: TwoProportionResult
    incremental_inr: Decimal
    ci_low_inr: Decimal
    ci_high_inr: Decimal
    cuped: CupedResult
    cuped_adjusted_inr: Decimal
    cost_per_inr_recovered: Decimal | None  # None when incremental_inr <= 0 -- undefined, not zero
    contacts_per_recovered_case_median: float | None


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def build_report(inputs: BatchInputs) -> HeadlineReport:
    significance = two_proportion_z_test(
        n_treated=inputs.n_treated,
        x_treated=inputs.x_treated,
        n_control=inputs.n_control,
        x_control=inputs.x_control,
    )
    incremental_inr = (
        Decimal(str(significance.lift)) * inputs.n_treated * inputs.mean_recovered_value_inr
    )
    ci_low_inr = (
        Decimal(str(significance.ci_low)) * inputs.n_treated * inputs.mean_recovered_value_inr
    )
    ci_high_inr = (
        Decimal(str(significance.ci_high)) * inputs.n_treated * inputs.mean_recovered_value_inr
    )

    cuped = cuped_adjust(
        treated_outcomes=inputs.treated_outcomes,
        treated_covariates=inputs.treated_covariates,
        control_outcomes=inputs.control_outcomes,
        control_covariates=inputs.control_covariates,
    )
    cuped_adjusted_inr = (
        Decimal(str(cuped.lift_adjusted)) * inputs.n_treated * inputs.mean_recovered_value_inr
    )

    cost_per_inr_recovered = (
        (inputs.spend_on_contact_inr / incremental_inr) if incremental_inr > 0 else None
    )

    return HeadlineReport(
        inputs=inputs,
        significance=significance,
        incremental_inr=incremental_inr,
        ci_low_inr=ci_low_inr,
        ci_high_inr=ci_high_inr,
        cuped=cuped,
        cuped_adjusted_inr=cuped_adjusted_inr,
        cost_per_inr_recovered=cost_per_inr_recovered,
        contacts_per_recovered_case_median=_median(inputs.contacts_per_resolved_case),
    )


def format_inr_whole(amount: Decimal) -> str:
    """Indian digit grouping (##,##,###), matching §9's own illustrative
    values exactly (e.g. "12,48,300"), not the international ###,###,### style."""
    rounded = int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    sign = "-" if rounded < 0 else ""
    digits = str(abs(rounded))
    if len(digits) <= 3:
        grouped = digits
    else:
        last3 = digits[-3:]
        rest = digits[:-3]
        parts: list[str] = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join([*parts, last3])
    return f"₹ {sign}{grouped}"


def render_headline_block(report: HeadlineReport) -> str:
    inputs = report.inputs
    sig = report.significance
    lines: list[str] = []
    lines.append(_DOUBLE_RULE)
    lines.append(
        f"RECOUP · BATCH {inputs.batch_id} · seed {inputs.seed} · {inputs.n_cases_total} cases"
    )
    lines.append(_RULE)
    lines.append(f"At risk                        {format_inr_whole(inputs.at_risk_inr)}")
    lines.append(
        f"Raw recovered (treated)        {format_inr_whole(inputs.raw_recovered_inr)}"
        "   ← overstates our impact"
    )
    lines.append(
        f"Incremental recovered          {format_inr_whole(report.incremental_inr)}"
        f"   (95% CI {format_inr_whole(report.ci_low_inr)} – {format_inr_whole(report.ci_high_inr)})"  # noqa: RUF001
    )
    significance_marker = "" if sig.significant else "   *** NOT STATISTICALLY SIGNIFICANT ***"
    lines.append(
        f"Lift                           {sig.lift * 100:.1f} pp       "
        f"z = {sig.z:.2f}, p = {sig.p_value:.4f}{significance_marker}"
    )
    lines.append(
        f"                               n_t = {sig.n_treated}  n_c = {sig.n_control}  "
        f"MDE = {sig.mde * 100:.1f} pp"
    )
    lines.append(
        f"CUPED-adjusted                 {format_inr_whole(report.cuped_adjusted_inr)}"
        "   (unadjusted shown above)"
    )
    lines.append(_RULE)
    lines.append(f"Spend on contact               {format_inr_whole(inputs.spend_on_contact_inr)}")
    cost_display = (
        f"₹ {report.cost_per_inr_recovered:.4f}"
        if report.cost_per_inr_recovered is not None
        else "undefined (no incremental recovery)"
    )
    lines.append(f"Cost per ₹ recovered           {cost_display}")
    blocked_breakdown = " · ".join(
        f"{reason} {count}" for reason, count in inputs.actions_blocked_by_policy.items()
    )
    saved_display = format_inr_whole(inputs.saved_by_not_contacting_inr)
    lines.append(
        f"₹ saved by not contacting      {saved_display}  (sure things + sleeping dogs + EV floor)"
    )
    lines.append(_RULE)
    total_blocked = sum(inputs.actions_blocked_by_policy.values())
    lines.append(f"Actions blocked by policy      {total_blocked}   ({blocked_breakdown})")
    median_display = (
        f"{report.contacts_per_recovered_case_median:.1f} median"
        if report.contacts_per_recovered_case_median is not None
        else "n/a (no resolved treated cases)"
    )
    lines.append(
        f"Contacts per recovered case    {median_display}    ·  "
        f"max touches respected: {inputs.max_touches_respected_rate * 100:.0f}%"
    )
    triage_note = (
        "all triaged, none lost" if inputs.exception_queue_all_triaged else "TRIAGE INCOMPLETE"
    )
    lines.append(
        f"Cases in exception queue       {inputs.cases_in_exception_queue}    ({triage_note})"
    )
    chain_status = "VERIFIED" if inputs.audit_chain_verified else "**BROKEN**"
    replay_status = "PASS" if inputs.replay_equality_passed else "**FAIL**"
    lines.append(f"Audit chain                    {chain_status} · replay equality {replay_status}")
    lines.append(_DOUBLE_RULE)
    return "\n".join(lines)


def to_json(report: HeadlineReport) -> str:
    inputs = report.inputs
    sig = report.significance
    payload = {
        "batch_id": inputs.batch_id,
        "seed": inputs.seed,
        "n_cases_total": inputs.n_cases_total,
        "at_risk_inr": str(inputs.at_risk_inr),
        "raw_recovered_inr": str(inputs.raw_recovered_inr),
        "incremental_inr": str(report.incremental_inr),
        "ci_low_inr": str(report.ci_low_inr),
        "ci_high_inr": str(report.ci_high_inr),
        "lift_pp": sig.lift * 100,
        "z": sig.z,
        "p_value": sig.p_value,
        "significant": sig.significant,
        "n_treated": sig.n_treated,
        "n_control": sig.n_control,
        "mde_pp": sig.mde * 100,
        "cuped_adjusted_inr": str(report.cuped_adjusted_inr),
        "cuped_theta": report.cuped.theta,
        "spend_on_contact_inr": str(inputs.spend_on_contact_inr),
        "cost_per_inr_recovered": (
            str(report.cost_per_inr_recovered)
            if report.cost_per_inr_recovered is not None
            else None
        ),
        "saved_by_not_contacting_inr": str(inputs.saved_by_not_contacting_inr),
        "actions_blocked_by_policy": inputs.actions_blocked_by_policy,
        "contacts_per_recovered_case_median": report.contacts_per_recovered_case_median,
        "max_touches_respected_rate": inputs.max_touches_respected_rate,
        "cases_in_exception_queue": inputs.cases_in_exception_queue,
        "exception_queue_all_triaged": inputs.exception_queue_all_triaged,
        "audit_chain_verified": inputs.audit_chain_verified,
        "replay_equality_passed": inputs.replay_equality_passed,
        "exclusions": inputs.exclusions,
        "breakdowns": [
            {
                "dimension": row.dimension,
                "key": row.key,
                "lift_pp": row.result.lift * 100,
                "p_value": row.result.p_value,
                "significant": row.result.significant,
                "n_treated": row.result.n_treated,
                "n_control": row.result.n_control,
            }
            for row in inputs.breakdowns
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def to_markdown(report: HeadlineReport) -> str:
    inputs = report.inputs
    sig = report.significance
    significance_note = "significant" if sig.significant else "**NOT statistically significant**"
    lines = [
        f"# Recoup — batch `{inputs.batch_id}` (seed {inputs.seed}, {inputs.n_cases_total} cases)",
        "",
        f"- At risk: {format_inr_whole(inputs.at_risk_inr)}",
        f"- Raw recovered (treated): {format_inr_whole(inputs.raw_recovered_inr)} "
        "(overstates impact)",
        f"- **Incremental recovered: {format_inr_whole(report.incremental_inr)}** "
        f"(95% CI {format_inr_whole(report.ci_low_inr)} – {format_inr_whole(report.ci_high_inr)})",  # noqa: RUF001
        f"- Lift: {sig.lift * 100:.1f} pp, z = {sig.z:.2f}, p = {sig.p_value:.4f} "
        f"({significance_note})",
        f"- n_t = {sig.n_treated}, n_c = {sig.n_control}, MDE = {sig.mde * 100:.1f} pp",
        f"- CUPED-adjusted: {format_inr_whole(report.cuped_adjusted_inr)} (unadjusted shown above)",
        "",
        "## Cost",
        "",
        f"- Spend on contact: {format_inr_whole(inputs.spend_on_contact_inr)}",
        "- Cost per ₹ recovered: "
        + (
            f"₹ {report.cost_per_inr_recovered:.4f}"
            if report.cost_per_inr_recovered is not None
            else "undefined (no incremental recovery)"
        ),
        f"- ₹ saved by not contacting: {format_inr_whole(inputs.saved_by_not_contacting_inr)} "
        "(sure things + sleeping dogs + EV floor)",
        "",
        "## Governance",
        "",
        f"- Actions blocked by policy: {sum(inputs.actions_blocked_by_policy.values())} "
        f"({', '.join(f'{k} {v}' for k, v in inputs.actions_blocked_by_policy.items())})",
        f"- Cases in exception queue: {inputs.cases_in_exception_queue} "
        f"({'all triaged' if inputs.exception_queue_all_triaged else 'TRIAGE INCOMPLETE'})",
        f"- Audit chain: {'VERIFIED' if inputs.audit_chain_verified else 'BROKEN'}, "
        f"replay equality {'PASS' if inputs.replay_equality_passed else 'FAIL'}",
    ]
    if inputs.breakdowns:
        lines += [
            "",
            "## Breakdowns",
            "",
            "| Dimension | Key | Lift (pp) | p | Significant |",
            "|---|---|---|---|---|",
        ]
        for row in inputs.breakdowns:
            lines.append(
                f"| {row.dimension} | {row.key} | {row.result.lift * 100:.1f} | "
                f"{row.result.p_value:.4f} | {row.result.significant} |"
            )
    return "\n".join(lines)
