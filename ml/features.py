"""Training-side feature frame: wraps `recoup.understanding.features.extract_features`
(the same function inference uses — see that module's docstring for why) and adds
the ground-truth columns a training script legitimately needs alongside features.

The ground-truth columns here (`true_root_cause`, `p_self_heal`,
`p_recover_by_channel`) are not part of FEATURE_COLUMNS and never reach a model's
`.fit(X, ...)` call as part of X — the leakage contract (see
`tests/unit/test_generator.py`) is about the *ingested payload*, not about a
training script's own dataframe, which needs labels next to features like any
supervised-learning script does.
"""

from __future__ import annotations

import pandas as pd

from recoup.data.generate import GeneratedBatch
from recoup.understanding.features import (
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    NUMERIC_COLUMNS,
    extract_features,
)

__all__ = ["CATEGORICAL_COLUMNS", "FEATURE_COLUMNS", "NUMERIC_COLUMNS", "build_feature_frame"]


def build_feature_frame(batch: GeneratedBatch) -> pd.DataFrame:
    rows = []
    for intake, truth in zip(batch.intake, batch.ground_truth, strict=True):
        features = extract_features(
            source_type=intake.source_type,
            merchant_id=intake.merchant_id,
            amount_at_risk=intake.amount_at_risk,
            occurred_at=intake.occurred_at,
            detail=intake.detail,
        )
        rows.append(
            {
                "provider_event_id": intake.provider_event_id,
                **features,
                "true_root_cause": truth.true_root_cause,
                "p_self_heal": truth.p_self_heal,
                "p_recover_by_channel": truth.p_recover_by_channel,
            }
        )
    frame = pd.DataFrame(rows)
    for col in CATEGORICAL_COLUMNS:
        frame[col] = frame[col].astype("category")
    return frame
