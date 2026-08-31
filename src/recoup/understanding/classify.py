"""FR-2: root-cause classification with calibrated confidence and SHAP attribution.

`checkout_abandonment` and `receivable_overdue` are resolved deterministically from
source_type — see `ml/train_classifier.py`'s docstring for why those were never
part of the trained classifier's scope. Everything else goes through the model,
then FR-2.6's confidence floor: below it, the case is classified `unknown` and
routed to the conservative ladder rather than guessed into an aggressive one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import shap

from recoup.understanding.artifacts import classifier_calibrator, classifier_model
from recoup.understanding.features import CATEGORICAL_COLUMNS, FEATURE_COLUMNS, extract_features

CONFIDENCE_FLOOR = 0.40
_DETERMINISTIC_SOURCES = {"checkout_abandonment", "receivable_overdue"}


@dataclass(frozen=True)
class ClassificationResult:
    root_cause: str
    confidence: float
    model_version: str | None  # None for the deterministic (non-model) sources
    shap_top_features: dict[str, float]
    cold_start: bool  # always True in this build — see the classifier's model card


def _classifier_model_version() -> str | None:
    metrics_path = Path("ml/artifacts/classifier/metrics.json")
    if not metrics_path.exists():
        return None
    version = json.loads(metrics_path.read_text(encoding="utf-8")).get("model_version")
    return str(version) if version is not None else None


def classify(
    *,
    source_type: str,
    merchant_id: str,
    amount_at_risk: Decimal | float,
    occurred_at: datetime,
    detail: dict[str, Any],
) -> ClassificationResult:
    if source_type in _DETERMINISTIC_SOURCES:
        return ClassificationResult(
            root_cause=source_type,
            confidence=1.0,
            model_version=None,
            shap_top_features={},
            cold_start=True,
        )

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

    model = classifier_model()
    calibrator = classifier_calibrator()
    raw_proba = model.predict_proba(row[FEATURE_COLUMNS])
    calibrated = calibrator.transform(raw_proba)[0]

    class_labels: list[str] = list(model.classes_)
    best_index = int(calibrated.argmax())
    root_cause = class_labels[best_index]
    confidence = float(calibrated[best_index])

    if confidence < CONFIDENCE_FLOOR:
        root_cause = "unknown"

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(row[FEATURE_COLUMNS])
    if hasattr(shap_values, "ndim") and shap_values.ndim == 3:
        per_class = shap_values[0, :, best_index]
    else:
        per_class = shap_values[best_index][0]
    shap_top = dict(
        sorted(
            zip(FEATURE_COLUMNS, (float(v) for v in per_class), strict=True),
            key=lambda kv: abs(kv[1]),
            reverse=True,
        )[:5]
    )

    return ClassificationResult(
        root_cause=root_cause,
        confidence=confidence,
        model_version=_classifier_model_version(),
        shap_top_features=shap_top,
        cold_start=True,
    )
