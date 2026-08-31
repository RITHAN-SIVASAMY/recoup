"""Orchestrates Phase 03 scoring for one case: classify, then uplift/relationship/priority.

Two events, both through `EventStore.append` — the only write path for case state.
Every score carries the `model_versions` that produced it (FR-3.6: "scores are
versioned so an old decision can be explained with the score it actually used").

Channel-specific treated propensity (FR-3.2) is deliberately not part of this
automatic pipeline — it needs a candidate channel to price, which doesn't exist
until Phase 06's bandit picks one. `understanding.propensity.score_propensity` is
there for that later call; this module only ever calls the channel-agnostic uplift
model, matching `ml/train_uplift.py`'s own scope decision.
"""

from __future__ import annotations

from decimal import Decimal

from recoup.audit.event_store import EventStore
from recoup.domain.models import Actor
from recoup.understanding.classify import ClassificationResult, classify
from recoup.understanding.priority import priority_score
from recoup.understanding.relationship import RelationshipScore, score_relationship
from recoup.understanding.uplift import UpliftResult, score_uplift

_INTAKE_ONLY_KEYS = {
    "source_type",
    "provider_event_id",
    "merchant_id",
    "amount_at_risk",
    "currency",
    "customer_ref",
}


async def score_case(event_store: EventStore, case_id: str) -> None:
    events = await event_store.events_for(case_id)
    created = next((e for e in events if e.event_type == "case.created"), None)
    if created is None:
        raise ValueError(f"case {case_id} has no case.created event yet; nothing to score")

    payload = created.payload
    source_type = payload["source_type"]
    merchant_id = payload["merchant_id"]
    amount_at_risk = Decimal(payload["amount_at_risk"])
    detail = {k: v for k, v in payload.items() if k not in _INTAKE_ONLY_KEYS}

    classification = classify(
        source_type=source_type,
        merchant_id=merchant_id,
        amount_at_risk=amount_at_risk,
        occurred_at=created.occurred_at,
        detail=detail,
    )
    await _append_classified(event_store, case_id, classification)

    uplift_result = score_uplift(
        source_type=source_type,
        merchant_id=merchant_id,
        amount_at_risk=amount_at_risk,
        occurred_at=created.occurred_at,
        detail=detail,
    )
    relationship = score_relationship(merchant_id=merchant_id, amount_at_risk=amount_at_risk)
    priority = priority_score(
        uplift=uplift_result.uplift,
        amount_at_risk=amount_at_risk,
        occurred_at=created.occurred_at,
        relationship_weight=relationship.relationship_weight,
    )
    await _append_scored(event_store, case_id, uplift_result, relationship, priority)


async def _append_classified(
    event_store: EventStore, case_id: str, classification: ClassificationResult
) -> None:
    model_versions = (
        {"classifier": classification.model_version} if classification.model_version else None
    )
    actor_identifier = classification.model_version or f"deterministic:{classification.root_cause}"
    await event_store.append(
        case_id=case_id,
        event_type="case.classified",
        payload={
            "root_cause": classification.root_cause,
            "confidence": classification.confidence,
            "cold_start": classification.cold_start,
            "shap_top_features": classification.shap_top_features,
        },
        actor=Actor(kind="model", identifier=actor_identifier),
        model_versions=model_versions,
    )


async def _append_scored(
    event_store: EventStore,
    case_id: str,
    uplift_result: UpliftResult,
    relationship: RelationshipScore,
    priority: float,
) -> None:
    await event_store.append(
        case_id=case_id,
        event_type="case.scored",
        payload={
            "p_recover_baseline": uplift_result.baseline_propensity,
            "uplift": uplift_result.uplift,
            "uplift_segment": uplift_result.segment,
            "relationship_weight": relationship.relationship_weight,
            "trust_score": relationship.trust_score,
            "priority": priority,
        },
        actor=Actor(kind="model", identifier=uplift_result.model_version),
        model_versions={"uplift": uplift_result.model_version},
    )
