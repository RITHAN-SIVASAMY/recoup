"""FR-3.3/3.4: uplift scoring and segmentation (X-learner).

Uses its own `mu0` (loaded from `ml/artifacts/uplift/`), not
`propensity.score_propensity`'s baseline model — `ml/train_uplift.py`'s docstring
explains why the X-learner trains its own channel-agnostic base models rather than
reusing the channel-aware ones. `baseline_propensity` is `mu0`'s isotonic-calibrated
prediction (CLAUDE.md rule 8: no model output bypasses calibration) — `tau0`/`tau1`
themselves are continuous treatment-effect regressions, not probabilities, so there
is nothing to calibrate on the uplift number itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from recoup.understanding.artifacts import uplift_component
from recoup.understanding.features import CATEGORICAL_COLUMNS, FEATURE_COLUMNS, extract_features

# Kept identical to ml/train_uplift.py's segmentation thresholds — see that
# module's docstring for what each one means and why.
SURE_THING_BASELINE = 0.60
SLEEPING_DOG_UPLIFT = -0.02
LOST_CAUSE_UPLIFT = 0.05

UpliftSegment = str  # "persuadable" | "sure_thing" | "lost_cause" | "sleeping_dog"


@dataclass(frozen=True)
class UpliftResult:
    uplift: float
    baseline_propensity: float
    segment: UpliftSegment
    model_version: str


def segment_for(baseline_propensity: float, uplift: float) -> UpliftSegment:
    if uplift < SLEEPING_DOG_UPLIFT:
        return "sleeping_dog"
    if baseline_propensity >= SURE_THING_BASELINE:
        return "sure_thing"
    if uplift <= LOST_CAUSE_UPLIFT:
        return "lost_cause"
    return "persuadable"


def _model_version() -> str:
    metrics_path = Path("ml/artifacts/uplift/metrics.json")
    return str(json.loads(metrics_path.read_text(encoding="utf-8"))["model_version"])


def score_uplift(
    *,
    source_type: str,
    merchant_id: str,
    amount_at_risk: Decimal | float,
    occurred_at: datetime,
    detail: dict[str, Any],
) -> UpliftResult:
    features = extract_features(
        source_type=source_type,
        merchant_id=merchant_id,
        amount_at_risk=amount_at_risk,
        occurred_at=occurred_at,
        detail=detail,
    )
    row = pd.DataFrame([features])
    for col in CATEGORICAL_COLUMNS:
        row[col] = row[col].astype("category")

    mu0 = uplift_component("mu0")
    mu0_calibrator = uplift_component("mu0_calibrator")
    tau0 = uplift_component("tau0")
    tau1 = uplift_component("tau1")

    raw_baseline = mu0.predict_proba(row[FEATURE_COLUMNS])[:, 1]
    baseline = float(mu0_calibrator.predict(raw_baseline)[0])
    g = 0.5  # treatment propensity — a fair coin flip in this batch, see the model card
    tau = float(
        g * tau0.predict(row[FEATURE_COLUMNS])[0] + (1 - g) * tau1.predict(row[FEATURE_COLUMNS])[0]
    )

    return UpliftResult(
        uplift=tau,
        baseline_propensity=baseline,
        segment=segment_for(baseline, tau),
        model_version=_model_version(),
    )
