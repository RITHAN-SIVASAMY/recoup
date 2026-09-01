"""FR-13.1/13.3/13.4: stratified cohort assignment, immutable, recorded as
`case.cohort_assigned` before any scoring happens.

Two spec constraints are in real tension and this module's design is how
they are reconciled: FR-13.1 requires the cohort to be assigned *before any
scoring*, while FR-13.3 requires stratifying by "root cause ... and segment"
-- both of which, in the rest of this codebase, are *outputs* of scoring
(`understanding.classify`, `understanding.uplift`). They cannot both be
scoring outputs and be available before scoring runs. This module resolves
that by stratifying on cheap, intake-observable proxies instead, available
the instant `case.created` lands, with zero model inference:

  * root cause  -> `source_type` (the coarse pre-classification signal the
    generator itself uses as ground truth for the two source types where
    root cause needs no classifier at all -- see `data/generate.py`)
  * segment     -> `merchant_id` (the merchant/customer-mix axis
    `docs/05-EVALUATION-PROTOCOL.md` §8 already reports breakdowns by:
    "Multiple synthetic merchant profiles ... cross-profile results
    reported")
  * amount band -> `amount_at_risk`, bucketed into fixed ₹ tiers

Legal-risk exclusion (FR-13.4) is likewise resolved with an intake-observable
proxy rather than a classifier: a `payment_failure` case whose raw gateway
decline reason is `risk_declined` (the issuer/gateway's own flag, present in
the payload at `case.created` -- not a model inference) is excluded from
control, the same way a case above the merchant's value cap is.

Assignment is batch-mode stratified: within each stratum, cases are ranked
by a seeded, auditable hash of `case_id + salt` and the first
`round(holdout_rate * stratum_size)` in that ranking become `control` --
exactly `holdout_rate` of each stratum, not merely `holdout_rate` in
expectation, which is the entire point of stratifying at small batch sizes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from recoup.audit.event_store import EventStore
from recoup.domain.models import Actor, Cohort

_SYSTEM = Actor(kind="system", identifier="measurement.cohort")

# The payment gateway's own raw decline reason (see data/distributions.py),
# never a classifier output -- checking it preserves the "before any
# scoring" ordering FR-13.1 requires.
_LEGAL_RISK_DECLINE_REASONS = frozenset({"risk_declined"})

_AMOUNT_BAND_CEILINGS: tuple[tuple[str, Decimal], ...] = (
    ("under_1k", Decimal("1000")),
    ("1k_10k", Decimal("10000")),
    ("10k_1l", Decimal("100000")),
)
_AMOUNT_BAND_OVER = "over_1l"


def amount_band(amount_at_risk: Decimal) -> str:
    for label, ceiling in _AMOUNT_BAND_CEILINGS:
        if amount_at_risk < ceiling:
            return label
    return _AMOUNT_BAND_OVER


@dataclass(frozen=True)
class Stratum:
    root_cause_proxy: str
    amount_band: str
    merchant_segment: str


@dataclass(frozen=True)
class CaseForAssignment:
    case_id: str
    source_type: str
    amount_at_risk: Decimal
    merchant_id: str
    error_reason: str | None = None  # payment_failure's raw decline reason, if any


@dataclass(frozen=True)
class CohortAssignment:
    case_id: str
    cohort: Cohort
    stratum: Stratum
    excluded_from_control: bool
    exclusion_reason: str | None
    rank_key: str  # sha256(case_id + salt) -- auditable: a reviewer can recompute this exactly


def stratum_for(case: CaseForAssignment) -> Stratum:
    return Stratum(
        root_cause_proxy=case.source_type,
        amount_band=amount_band(case.amount_at_risk),
        merchant_segment=case.merchant_id,
    )


def _exclusion_reason(case: CaseForAssignment, *, value_cap_inr: Decimal) -> str | None:
    if case.amount_at_risk > value_cap_inr:
        return f"amount_at_risk {case.amount_at_risk} exceeds value_cap_inr {value_cap_inr}"
    if case.error_reason in _LEGAL_RISK_DECLINE_REASONS:
        return f"legal-risk decline reason: {case.error_reason}"
    return None


def _rank_key(case_id: str, salt: str) -> str:
    return hashlib.sha256(f"{case_id}:{salt}".encode()).hexdigest()


def assign_cohorts(
    cases: list[CaseForAssignment], *, holdout_rate: Decimal, value_cap_inr: Decimal, salt: str
) -> list[CohortAssignment]:
    if not (Decimal(0) <= holdout_rate <= Decimal(1)):
        raise ValueError(f"holdout_rate must be in [0, 1], got {holdout_rate}")

    excluded_reasons: dict[str, str] = {}
    by_stratum: dict[Stratum, list[CaseForAssignment]] = {}
    for case in cases:
        reason = _exclusion_reason(case, value_cap_inr=value_cap_inr)
        if reason is not None:
            excluded_reasons[case.case_id] = reason
            continue
        by_stratum.setdefault(stratum_for(case), []).append(case)

    control_ids: set[str] = set()
    for stratum_cases in by_stratum.values():
        ranked = sorted(stratum_cases, key=lambda c: _rank_key(c.case_id, salt))
        n_control = round(float(holdout_rate) * len(ranked))
        control_ids.update(c.case_id for c in ranked[:n_control])

    assignments: list[CohortAssignment] = []
    for case in cases:
        stratum = stratum_for(case)
        rank_key = _rank_key(case.case_id, salt)
        if case.case_id in excluded_reasons:
            assignments.append(
                CohortAssignment(
                    case_id=case.case_id,
                    cohort="treatment",
                    stratum=stratum,
                    excluded_from_control=True,
                    exclusion_reason=excluded_reasons[case.case_id],
                    rank_key=rank_key,
                )
            )
            continue
        cohort: Cohort = "control" if case.case_id in control_ids else "treatment"
        assignments.append(
            CohortAssignment(
                case_id=case.case_id,
                cohort=cohort,
                stratum=stratum,
                excluded_from_control=False,
                exclusion_reason=None,
                rank_key=rank_key,
            )
        )
    return assignments


async def record_assignment(
    event_store: EventStore, assignment: CohortAssignment, *, policy_version: str
) -> None:
    await event_store.append(
        case_id=assignment.case_id,
        event_type="case.cohort_assigned",
        payload={
            "cohort": assignment.cohort,
            "stratum": {
                "root_cause_proxy": assignment.stratum.root_cause_proxy,
                "amount_band": assignment.stratum.amount_band,
                "merchant_segment": assignment.stratum.merchant_segment,
            },
            "excluded_from_control": assignment.excluded_from_control,
            "exclusion_reason": assignment.exclusion_reason,
            "rank_key": assignment.rank_key,
        },
        actor=_SYSTEM,
        policy_version=policy_version,
    )
