"""Train the FR-3.1/3.2 baseline (control-arm) and treated (treatment-arm) propensity models.

Outcomes are bootstrapped from the generator's ground-truth response curves — see
`ml/outcomes.py`'s docstring for why that's legitimate methodology, not leakage.
Both models train on the realized 0/1 `recovered` outcome only.

Run: `uv run python ml/train_propensity.py` (also behind `make train`).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import CATEGORICAL_COLUMNS, FEATURE_COLUMNS, build_feature_frame

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from outcomes import realize_outcomes
from recoup.data.generate import generate_batch
from recoup.understanding.calibration import binary_calibrator

TRAIN_SEED = 20260302  # distinct from the classifier's seed
N_CASES = 24000
ARTIFACT_ROOT = Path("ml/artifacts")
CARD_PATH = Path("ml/cards/propensity.md")
AUC_GATE = 0.70


def _content_hash(path: Path, salt: str) -> str:
    return hashlib.sha256(path.read_bytes() + salt.encode()).hexdigest()[:16]


def _plot_roc(fpr: np.ndarray, tpr: np.ndarray, auc: float, title: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "k--", label="random")
    ax.plot(fpr, tpr, label=f"AUC = {auc:.3f}")
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _train_one_arm(arm_df: pd.DataFrame, name: str, feature_columns: list[str]) -> dict[str, Any]:
    out_dir = ARTIFACT_ROOT / f"propensity_{name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    train, temp = train_test_split(
        arm_df, test_size=0.30, stratify=arm_df["recovered"], random_state=TRAIN_SEED
    )
    val, test = train_test_split(
        temp, test_size=0.50, stratify=temp["recovered"], random_state=TRAIN_SEED
    )

    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        random_state=TRAIN_SEED,
        verbosity=-1,
    )
    model.fit(train[feature_columns], train["recovered"])

    val_proba = model.predict_proba(val[feature_columns])[:, 1]
    calibrator = binary_calibrator(val_proba, val["recovered"].to_numpy())

    test_proba_raw = model.predict_proba(test[feature_columns])[:, 1]
    test_proba = calibrator.predict(test_proba_raw)
    y_test = test["recovered"].to_numpy()

    auc = float(roc_auc_score(y_test, test_proba))
    pr_auc = float(average_precision_score(y_test, test_proba))
    fpr, tpr, _ = roc_curve(y_test, test_proba)
    _plot_roc(fpr, tpr, auc, f"Propensity ({name}) — ROC (test set)", out_dir / "roc_curve.png")

    joblib.dump(model, out_dir / "model.joblib")
    joblib.dump(calibrator, out_dir / "calibrator.joblib")
    model_version = f"propensity-{name}-{_content_hash(out_dir / 'model.joblib', str(TRAIN_SEED))}"

    metrics = {
        "model_version": model_version,
        "arm": name,
        "feature_columns": feature_columns,
        "train_seed": TRAIN_SEED,
        "n_train": len(train),
        "n_val": len(val),
        "n_test": len(test),
        "base_rate": float(arm_df["recovered"].mean()),
        "auc_roc": auc,
        "pr_auc": pr_auc,
        "gate": {"auc_min": AUC_GATE},
        "gate_passed": bool(auc >= AUC_GATE),
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"[{name}] AUC-ROC: {auc:.4f} (gate >= {AUC_GATE})  PR-AUC: {pr_auc:.4f}")
    return metrics


def _write_model_card(baseline: dict[str, Any], treated: dict[str, Any]) -> None:
    card = f"""# Model card — propensity (baseline and treated)

## What it does
Two independent binary classifiers per FR-3.1/3.2:
- **baseline** — P(recover | case, no intervention): trained on the synthetic
  control arm's realized outcomes.
- **treated** — P(recover | case, intervention, channel): trained on the synthetic
  treatment arm's realized outcomes, with the (randomly-assigned) channel used for
  that case as an explicit feature — FR-3.2's own definition includes channel as a
  conditioning variable, and it is one here, not folded into an average.

Outcomes are bootstrapped from the generator's ground-truth response curves
(`ml/outcomes.py`) — a case's cohort and its 0/1 recovery outcome are both
*realized* stochastically from `p_self_heal`/`p_recover_by_channel`, then that
realized outcome (never the underlying probability) is what each model trains on.

## Data
{baseline["n_train"] + baseline["n_val"] + baseline["n_test"]} control-arm and
{treated["n_train"] + treated["n_val"] + treated["n_test"]} treatment-arm cases
(seed {baseline["train_seed"]}), each split 70/15/15 (stratified on the outcome).
Base recovery rate: {baseline["base_rate"]:.3f} (control) vs {treated["base_rate"]:.3f} (treated) —
the treated arm's higher rate is exactly the aggregate uplift signal Phase 03's
uplift model is trying to attribute per case, not just on average.

## Metrics (held-out test set)
| Arm | AUC-ROC | PR-AUC | Gate |
|---|---|---|---|
| baseline | {baseline["auc_roc"]:.4f} | {baseline["pr_auc"]:.4f} | {"PASS" if baseline["gate_passed"] else "FAIL"} (>= {AUC_GATE}) |
| treated | {treated["auc_roc"]:.4f} | {treated["pr_auc"]:.4f} | {"PASS" if treated["gate_passed"] else "FAIL"} (>= {AUC_GATE}) |

ROC curves: `ml/artifacts/propensity_baseline/roc_curve.png`,
`ml/artifacts/propensity_treated/roc_curve.png`.

## Known failure modes
- **Bootstrapped, not observed, outcomes.** Every label here comes from realizing
  the synthetic generator's own probabilities — this validates that the modeling
  *pipeline* can recover a known signal, not that it will perform this well on
  real historical outcomes, which do not exist yet for this system.
- **Channel choice in the treatment arm is uniform-random**, not the constrained
  bandit FR-9.2 specifies (that lands in Phase 06). `channel` is a real feature
  here, but its *distribution in the training data* reflects "pick any channel with
  equal probability," not what a live bandit would actually select — the model
  will need retraining once real channel-selection data exists, or it will have
  learned a channel-effectiveness pattern from an unrealistic assignment policy.
- **Same cold-start limitation as the classifier**: no repeat-customer history.
- **What would fix it:** real observed outcomes (as soon as Phase 06+10 exist to
  produce them) replacing the bootstrap, trained on the bandit's actual channel
  assignments rather than a uniform-random stand-in.
"""
    CARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    CARD_PATH.write_text(card, encoding="utf-8")


def main() -> int:
    batch = generate_batch(seed=TRAIN_SEED, n_cases=N_CASES)
    frame = build_feature_frame(batch)
    for col in CATEGORICAL_COLUMNS:
        frame[col] = frame[col].cat.remove_unused_categories()

    realized = realize_outcomes(frame, seed=TRAIN_SEED)
    control = realized[realized["cohort"] == "control"].copy()
    treated = realized[realized["cohort"] == "treatment"].copy()
    treated["channel"] = treated["channel"].astype("category")

    # FR-3.2 defines treated propensity as P(recover | case, intervention, channel,
    # timing) — channel is a real conditioning variable here, not an afterthought.
    # It's meaningless for the control arm (no intervention happened), so baseline
    # doesn't get it.
    baseline_metrics = _train_one_arm(control, "baseline", FEATURE_COLUMNS)
    treated_metrics = _train_one_arm(treated, "treated", [*FEATURE_COLUMNS, "channel"])
    _write_model_card(baseline_metrics, treated_metrics)

    gate_passed = baseline_metrics["gate_passed"] and treated_metrics["gate_passed"]
    return 0 if gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
