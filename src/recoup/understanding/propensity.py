"""FR-3.1/3.2: baseline and treated propensity scoring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from recoup.understanding.artifacts import propensity_calibrator, propensity_model
from recoup.understanding.features import CATEGORICAL_COLUMNS, FEATURE_COLUMNS, extract_features


@dataclass(frozen=True)
class PropensityResult:
    p_recover_baseline: float
    p_recover_treated: float
    model_version_baseline: str
    model_version_treated: str


@lru_cache
def _model_version(arm: str) -> str:
    metrics_path = Path(f"ml/artifacts/propensity_{arm}/metrics.json")
    return str(json.loads(metrics_path.read_text(encoding="utf-8"))["model_version"])


def _score_arm(row: pd.DataFrame, arm: str, feature_columns: list[str]) -> float:
    model = propensity_model(arm)
    calibrator = propensity_calibrator(arm)
    raw = model.predict_proba(row[feature_columns])[:, 1]
    return float(calibrator.predict(raw)[0])


def score_propensity(
    *,
    source_type: str,
    merchant_id: str,
    amount_at_risk: Decimal | float,
    occurred_at: datetime,
    detail: dict[str, Any],
    channel: str,
) -> PropensityResult:
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

    baseline = _score_arm(row, "baseline", FEATURE_COLUMNS)

    treated_row = row.copy()
    treated_row["channel"] = pd.Categorical([channel])
    treated = _score_arm(treated_row, "treated", [*FEATURE_COLUMNS, "channel"])

    return PropensityResult(
        p_recover_baseline=baseline,
        p_recover_treated=treated,
        model_version_baseline=_model_version("baseline"),
        model_version_treated=_model_version("treated"),
    )
