"""Seeded synthetic batch generator.

`generate_batch()` is pure and deterministic: the same seed always produces the
same intake records and ground truth, in the same order, with no dependency on
wall-clock time. `main()` (behind `make data`) writes both to `data/generated/`
as hash-checkable JSON Lines and, by default, ingests the batch through the real
`ingest()` pipeline used by webhooks and CSV import — there is exactly one way a
case enters this system, synthetic or not.

Ground truth (`p_self_heal`, `p_recover_by_channel`) exists only to validate the
uplift model later (Phase 03) against a known answer. It is written to a separate
file, joinable only by `provider_event_id`, and is never part of a `NormalizedIntake`
— nothing a model could see at inference time carries it. See
`tests/unit/test_generator_ground_truth_leakage.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.event_store import EventStore, create_engine
from recoup.data.distributions import (
    CHANNEL_EFFECTIVENESS,
    DECLINE_REASONS,
    ISSUERS,
    PAYMENT_METHODS,
    archetype_weights_for,
    day_of_month_weight,
    hour_of_day_weight,
    mandate_root_cause,
    noisy_root_cause_for_decline,
    weighted_choice,
)
from recoup.data.merchants import MERCHANT_PROFILES, MerchantProfile
from recoup.ingestion.ingest import ingest
from recoup.ingestion.models import NormalizedIntake

# A fixed anchor, not "now" — reproducibility must not depend on when this runs.
_BATCH_REFERENCE_DATE = datetime(2026, 8, 1, tzinfo=UTC)
_WINDOW_DAYS = 30
_MAX_REJECTION_WEIGHT = 1.8 * 1.8
_MAX_REJECTION_ATTEMPTS = 200


class GroundTruth(BaseModel):
    """Validation-only truth for a generated case. Never reaches a model at inference.

    `true_root_cause` is `None` for checkout_abandonment/receivable_overdue, where
    source_type already determines it and there is nothing to classify.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_event_id: str
    p_self_heal: float
    p_recover_by_channel: dict[str, float]
    true_root_cause: str | None = None


@dataclass(frozen=True)
class GeneratedBatch:
    intake: list[NormalizedIntake]
    ground_truth: list[GroundTruth]


def _random_amount(rng: random.Random, amount_range: tuple[Decimal, Decimal]) -> Decimal:
    low, high = amount_range
    fraction = Decimal(str(round(rng.uniform(0.0, 1.0), 6)))
    return (low + (high - low) * fraction).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _random_occurred_at(rng: random.Random) -> datetime:
    candidate = _BATCH_REFERENCE_DATE
    for _ in range(_MAX_REJECTION_ATTEMPTS):
        days_back = rng.uniform(0, _WINDOW_DAYS)
        candidate = _BATCH_REFERENCE_DATE - timedelta(days=days_back)
        weight = day_of_month_weight(candidate.day) * hour_of_day_weight(candidate.hour)
        if rng.uniform(0, _MAX_REJECTION_WEIGHT) <= weight:
            return candidate
    return candidate  # exhausted the budget; the last draw is still a valid sample


def _ground_truth_values(rng: random.Random, archetype: str) -> tuple[float, dict[str, float]]:
    # Within-archetype ranges are deliberately narrower than a first cut: too wide,
    # and per-case p_self_heal is dominated by noise no feature could ever explain,
    # capping propensity/uplift AUC near chance regardless of model quality. These
    # are still ranges, not point values — real variance remains, just bounded.
    if archetype == "sure_thing":
        p_self_heal, bump = rng.uniform(0.75, 0.92), rng.uniform(0.0, 0.03)
    elif archetype == "lost_cause":
        p_self_heal, bump = rng.uniform(0.03, 0.11), rng.uniform(0.0, 0.03)
    elif archetype == "sleeping_dog":
        p_self_heal, bump = rng.uniform(0.32, 0.46), rng.uniform(-0.08, -0.02)
    else:  # persuadable
        p_self_heal, bump = rng.uniform(0.14, 0.32), rng.uniform(0.28, 0.42)

    p_recover_by_channel = {
        channel: round(min(max(p_self_heal + bump * effectiveness, 0.0), 0.98), 4)
        for channel, effectiveness in CHANNEL_EFFECTIVENESS.items()
    }
    return round(p_self_heal, 4), p_recover_by_channel


def _detail_for_source(
    rng: random.Random, source_type: str, seed: int, index: int, occurred_at: datetime
) -> tuple[dict[str, Any], str | None]:
    """Returns (detail for the ingested payload, true_root_cause for ground truth only)."""
    if source_type == "payment_failure":
        reason = weighted_choice(rng, DECLINE_REASONS)
        detail = {
            "order_id": f"order-{seed:04d}-{index:05d}",
            "method": weighted_choice(rng, PAYMENT_METHODS),
            "error_code": reason.upper(),
            "error_description": reason.replace("_", " "),
            "error_reason": reason,
            "issuer": weighted_choice(rng, ISSUERS),
        }
        return detail, noisy_root_cause_for_decline(rng, reason)
    if source_type == "mandate_failure":
        true_root_cause = mandate_root_cause(rng)
        # Two weakly-correlated observable signals, not a leak: a mandate that's
        # failed many times in a row and is sitting "halted" skews toward
        # "revoked"; one still-retrying failure skews toward "technical_failure".
        # Both relationships are soft (randint spread, probabilistic status), same
        # as the payment-failure confusion — the classifier has to learn the
        # tendency from two noisy features together, not read off a single answer.
        base_failures, halted_probability = {
            "mandate_technical_failure": (1, 0.30),
            "mandate_insufficient_balance": (3, 0.60),
            "mandate_revoked": (5, 0.90),
        }[true_root_cause]
        consecutive_failures = max(1, base_failures + rng.randint(-1, 1))
        mandate_detail: dict[str, Any] = {
            "plan_id": f"plan-{seed:04d}",
            "status": "halted" if rng.random() < halted_probability else "pending",
            "charge_at": None,
            "issuer": weighted_choice(rng, ISSUERS),
            "consecutive_failures": consecutive_failures,
        }
        return mandate_detail, true_root_cause
    if source_type == "checkout_abandonment":
        return {"initiated_method": weighted_choice(rng, PAYMENT_METHODS)}, None
    if source_type == "receivable_overdue":
        receivable_detail: dict[str, Any] = {
            "invoice_id": f"INV-{seed:04d}-{index:05d}",
            "due_date": occurred_at.date().isoformat(),
            "terms": "net-30",
            "days_overdue": max((_BATCH_REFERENCE_DATE - occurred_at).days, 0),
        }
        return receivable_detail, None
    raise ValueError(f"unknown source_type: {source_type!r}")


def _build_case(
    rng: random.Random, seed: int, index: int, profile: MerchantProfile
) -> tuple[NormalizedIntake, GroundTruth]:
    source_type = weighted_choice(rng, list(profile.source_type_weights.items()))
    occurred_at = _random_occurred_at(rng)
    provider_event_id = f"synthetic-{seed:04d}-{index:05d}"
    detail, true_root_cause = _detail_for_source(rng, source_type, seed, index, occurred_at)
    amount_at_risk = _random_amount(rng, profile.amount_range_inr)

    intake = NormalizedIntake(
        source_type=source_type,  # type: ignore[arg-type]
        provider_event_id=provider_event_id,
        merchant_id=profile.merchant_id,
        amount_at_risk=amount_at_risk,
        customer_ref=f"cust-{seed:04d}-{index:05d}",
        occurred_at=occurred_at,
        detail=detail,
    )

    low, high = profile.amount_range_inr
    relative_amount = float((amount_at_risk - low) / (high - low)) if high > low else 0.5
    decline_reason = detail.get("error_reason") if source_type == "payment_failure" else None
    archetype = weighted_choice(
        rng, archetype_weights_for(source_type, relative_amount, decline_reason)
    )
    p_self_heal, p_recover_by_channel = _ground_truth_values(rng, archetype)
    ground_truth = GroundTruth(
        provider_event_id=provider_event_id,
        p_self_heal=p_self_heal,
        p_recover_by_channel=p_recover_by_channel,
        true_root_cause=true_root_cause,
    )
    return intake, ground_truth


def generate_batch(*, seed: int, n_cases: int) -> GeneratedBatch:
    rng = random.Random(seed)
    intake: list[NormalizedIntake] = []
    ground_truth: list[GroundTruth] = []
    for index in range(n_cases):
        profile = MERCHANT_PROFILES[index % len(MERCHANT_PROFILES)]
        case_intake, case_ground_truth = _build_case(rng, seed, index, profile)
        intake.append(case_intake)
        ground_truth.append(case_ground_truth)
    return GeneratedBatch(intake=intake, ground_truth=ground_truth)


def _write_jsonl(path: Path, records: list[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            line = json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
            handle.write(line + "\n")


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def _ingest_batch(batch: GeneratedBatch, engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)
    for intake in batch.intake:
        async with session_factory() as session:
            await ingest(session, event_store, intake)


async def _ingest_and_dispose(batch: GeneratedBatch) -> None:
    engine = create_engine()
    try:
        await _ingest_batch(batch, engine)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cases", type=int, default=500)
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="only write data/generated/*.jsonl; do not touch the database",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("data/generated"))
    args = parser.parse_args()

    batch = generate_batch(seed=args.seed, n_cases=args.cases)

    intake_path = args.out_dir / "intake.jsonl"
    ground_truth_path = args.out_dir / "ground_truth.jsonl"
    _write_jsonl(intake_path, list(batch.intake))
    _write_jsonl(ground_truth_path, list(batch.ground_truth))

    print(f"generated {len(batch.intake)} cases (seed={args.seed})")
    print(f"  {intake_path}       sha256={_sha256_of(intake_path)}")
    print(f"  {ground_truth_path} sha256={_sha256_of(ground_truth_path)}")

    if not args.skip_ingest:
        asyncio.run(_ingest_and_dispose(batch))
        print(f"ingested {len(batch.intake)} cases into the database")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
