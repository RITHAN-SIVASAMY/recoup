"""CI metric gate for the ML models — fails the build if macro-F1 < .85, Brier > .12, any
propensity AUC < .70, or Qini <= 0.

Reads the metrics.json files `ml/train_*.py` write; does not retrain. CI's `models`
job runs the three training scripts first, so this checks what they actually
produced rather than re-deriving numbers — a script that silently retrains inside
the gate could hide a nondeterminism bug the gate exists to catch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ARTIFACT_ROOT = Path("ml/artifacts")


def _load(relative_path: str) -> dict:  # type: ignore[type-arg]
    path = ARTIFACT_ROOT / relative_path
    if not path.exists():
        print(f"metric_gate: {path} is missing — run `make train` first.")
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def main() -> int:
    classifier = _load("classifier/metrics.json")
    baseline = _load("propensity_baseline/metrics.json")
    treated = _load("propensity_treated/metrics.json")
    uplift = _load("uplift/metrics.json")

    checks = [
        (
            "classifier macro-F1",
            classifier["macro_f1"],
            ">=",
            classifier["gate"]["macro_f1_min"],
            classifier["macro_f1"] >= classifier["gate"]["macro_f1_min"],
        ),
        (
            "classifier Brier",
            classifier["brier_score"],
            "<=",
            classifier["gate"]["brier_max"],
            classifier["brier_score"] <= classifier["gate"]["brier_max"],
        ),
        (
            "propensity (baseline) AUC-ROC",
            baseline["auc_roc"],
            ">=",
            baseline["gate"]["auc_min"],
            baseline["gate_passed"],
        ),
        (
            "propensity (treated) AUC-ROC",
            treated["auc_roc"],
            ">=",
            treated["gate"]["auc_min"],
            treated["gate_passed"],
        ),
        (
            "uplift Qini coefficient",
            uplift["qini_coefficient"],
            ">",
            uplift["gate"]["qini_min"],
            uplift["gate_passed"],
        ),
    ]

    all_passed = True
    for name, value, comparator, threshold, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {value:.4f} {comparator} {threshold}")
        all_passed = all_passed and passed

    if all_passed:
        print("metric_gate: all model metrics cleared their gates.")
        return 0
    print("metric_gate: at least one model metric missed its gate.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
