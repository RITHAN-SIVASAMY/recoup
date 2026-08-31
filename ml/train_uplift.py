"""Train the FR-3.3 uplift model: an X-learner over two channel-agnostic base models.

Deliberately trains its own control/treated base models rather than reusing
`train_propensity.py`'s (channel-aware) treated model: FR-3.3's uplift score is
tau = P(recover|treated) - P(recover|untreated), which has no channel parameter —
reusing the channel-aware model would need a channel value for every counterfactual
prediction on the *other* arm, which doesn't exist for cases that were never
treated. `ml/cards/propensity.md` documents the channel-aware model separately.

Run: `uv run python ml/train_uplift.py` (also behind `make train`).
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
from scipy.stats import spearmanr
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import CATEGORICAL_COLUMNS, FEATURE_COLUMNS, build_feature_frame
from qini import compute_qini_curve, uplift_at_k

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from outcomes import realize_outcomes
from recoup.data.generate import generate_batch
from recoup.understanding.calibration import binary_calibrator

TRAIN_SEED = 20260303
N_CASES = 24000
ARTIFACT_DIR = Path("ml/artifacts/uplift")
CARD_PATH = Path("ml/cards/uplift.md")
QINI_GATE = 0.0
TREATMENT_PROPENSITY = 0.5  # cohort assignment is a fair coin flip in this batch

# Segmentation thresholds (see the domain glossary) — documented cutoffs, not
# learned: a case is a sure_thing if it's very likely to resolve on its own
# regardless of uplift; a sleeping_dog if contact is predicted to actively hurt;
# a lost_cause if neither self-heal nor our action gets it anywhere; everything
# else with real positive uplift is a persuadable — the only segment worth acting on.
SURE_THING_BASELINE = 0.60
SLEEPING_DOG_UPLIFT = -0.02
LOST_CAUSE_UPLIFT = 0.05


def _content_hash(path: Path, salt: str) -> str:
    return hashlib.sha256(path.read_bytes() + salt.encode()).hexdigest()[:16]


def _fit_binary(train: pd.DataFrame, target: str) -> lgb.LGBMClassifier:
    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=250,
        learning_rate=0.06,
        num_leaves=31,
        min_child_samples=15,
        random_state=TRAIN_SEED,
        verbosity=-1,
    )
    model.fit(train[FEATURE_COLUMNS], train[target])
    return model


def _fit_regressor(x: pd.DataFrame, y: pd.Series) -> lgb.LGBMRegressor:
    model = lgb.LGBMRegressor(
        n_estimators=200,
        learning_rate=0.06,
        num_leaves=15,
        min_child_samples=15,
        random_state=TRAIN_SEED,
        verbosity=-1,
    )
    model.fit(x[FEATURE_COLUMNS], y)
    return model


def segment(baseline_pred: np.ndarray, uplift_pred: np.ndarray) -> list[str]:
    labels = []
    for mu0, tau in zip(baseline_pred, uplift_pred, strict=True):
        if tau < SLEEPING_DOG_UPLIFT:
            labels.append("sleeping_dog")
        elif mu0 >= SURE_THING_BASELINE:
            labels.append("sure_thing")
        elif tau <= LOST_CAUSE_UPLIFT:
            labels.append("lost_cause")
        else:
            labels.append("persuadable")
    return labels


def _plot_qini(fractions: list[float], gains: list[float], qini: float, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, gains[-1]], "k--", label="random targeting")
    ax.plot(fractions, gains, label=f"model (Qini = {qini:.3f})")
    ax.set_xlabel("Fraction of population targeted (by predicted uplift, descending)")
    ax.set_ylabel("Cumulative incremental recoveries")
    ax.set_title("Uplift model — Qini curve (test set)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    batch = generate_batch(seed=TRAIN_SEED, n_cases=N_CASES)
    frame = build_feature_frame(batch)
    for col in CATEGORICAL_COLUMNS:
        frame[col] = frame[col].cat.remove_unused_categories()
    realized = realize_outcomes(frame, seed=TRAIN_SEED)

    train, temp = train_test_split(
        realized, test_size=0.30, stratify=realized["cohort"], random_state=TRAIN_SEED
    )
    val, test = train_test_split(
        temp, test_size=0.50, stratify=temp["cohort"], random_state=TRAIN_SEED
    )

    train_control = train[train["cohort"] == "control"]
    train_treated = train[train["cohort"] == "treatment"]
    val_control = val[val["cohort"] == "control"]

    # Stage 1: base propensity models (mu0, mu1), channel-agnostic.
    mu0 = _fit_binary(train_control, "recovered")
    mu1 = _fit_binary(train_treated, "recovered")

    # mu0's calibrated form is what understanding/uplift.py reports as
    # baseline_propensity (case.scored's p_recover_baseline) — CLAUDE.md rule 8:
    # no model output bypasses calibration. The X-learner's internal D0/D1 residual
    # computation below still uses mu0/mu1's raw scores, which is the standard,
    # narrower scope for that step (an implementation detail that never leaves this
    # script) — only what's actually exposed downstream needs to be calibrated.
    mu0_calibrator = binary_calibrator(
        mu0.predict_proba(val_control[FEATURE_COLUMNS])[:, 1], val_control["recovered"].to_numpy()
    )

    # Stage 2: imputed treatment effects, then regress each on features.
    d1 = (
        train_treated["recovered"].to_numpy()
        - mu0.predict_proba(train_treated[FEATURE_COLUMNS])[:, 1]
    )
    d0 = (
        mu1.predict_proba(train_control[FEATURE_COLUMNS])[:, 1]
        - train_control["recovered"].to_numpy()
    )
    tau1_model = _fit_regressor(train_treated, pd.Series(d1, index=train_treated.index))
    tau0_model = _fit_regressor(train_control, pd.Series(d0, index=train_control.index))

    def predict_tau(x: pd.DataFrame) -> np.ndarray:
        g = TREATMENT_PROPENSITY
        return g * tau0_model.predict(x[FEATURE_COLUMNS]) + (1 - g) * tau1_model.predict(
            x[FEATURE_COLUMNS]
        )

    # Held-out evaluation on `test` (mixed cohort, never touched during fitting).
    test_tau = predict_tau(test)
    test_baseline = mu0_calibrator.predict(mu0.predict_proba(test[FEATURE_COLUMNS])[:, 1])
    outcome = test["recovered"].to_numpy()
    is_treated = (test["cohort"] == "treatment").to_numpy()

    qini = compute_qini_curve(outcome, is_treated, test_tau)
    uplift_top20 = uplift_at_k(outcome, is_treated, test_tau, 0.20)

    ground_truth_tau = test.apply(
        lambda row: max(row["p_recover_by_channel"].values()) - row["p_self_heal"], axis=1
    ).to_numpy()
    ground_truth_agreement, _ = spearmanr(test_tau, ground_truth_tau)

    segments = segment(test_baseline, test_tau)
    segment_counts = pd.Series(segments).value_counts().to_dict()

    _plot_qini(qini.fractions, qini.gains, qini.qini_coefficient, ARTIFACT_DIR / "qini_curve.png")

    for name, model in [
        ("mu0", mu0),
        ("mu0_calibrator", mu0_calibrator),
        ("mu1", mu1),
        ("tau0", tau0_model),
        ("tau1", tau1_model),
    ]:
        joblib.dump(model, ARTIFACT_DIR / f"{name}.joblib")
    model_version = f"uplift-{_content_hash(ARTIFACT_DIR / 'tau1.joblib', str(TRAIN_SEED))}"

    metrics = {
        "model_version": model_version,
        "train_seed": TRAIN_SEED,
        "n_train": len(train),
        "n_val": len(val),
        "n_test": len(test),
        "qini_coefficient": qini.qini_coefficient,
        "uplift_at_top20pct": uplift_top20,
        "ground_truth_spearman": float(ground_truth_agreement),
        "segment_counts_test": segment_counts,
        "gate": {"qini_min": QINI_GATE},
        "gate_passed": bool(qini.qini_coefficient > QINI_GATE),
    }
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    _write_model_card(metrics)

    print(f"Qini coefficient: {qini.qini_coefficient:.4f} (gate > {QINI_GATE})")
    print(f"Uplift at top 20%: {uplift_top20:.4f}")
    print(f"Agreement with generator's ground-truth tau (Spearman): {ground_truth_agreement:.4f}")
    return 0 if metrics["gate_passed"] else 1


def _write_model_card(metrics: dict[str, Any]) -> None:
    segments = "\n".join(
        f"| {label} | {count} |" for label, count in metrics["segment_counts_test"].items()
    )
    card = f"""# Model card — uplift (X-learner)

## What it does
Estimates tau(case) = P(recover \\| treated) - P(recover \\| untreated) per FR-3.3, via
an X-learner (ADR-0007) over two channel-agnostic LightGBM base models (control-arm
`mu0`, treated-arm `mu1`), then two regressors on the imputed treatment effects
(`tau0` fit on control-arm residuals, `tau1` on treated-arm residuals), combined as
τ(x) = 0.5·tau0(x) + 0.5·tau1(x) — 0.5 because cohort assignment in this batch is
an unweighted coin flip, so that's the real treatment propensity g(x). `mu0`'s
reported/exposed predictions are isotonic-calibrated (`mu0_calibrator`, fit on a
held-out control-arm validation split) before anything downstream sees them —
`tau0`/`tau1`'s internal imputed-residual training step uses `mu0`/`mu1`'s raw
scores, the standard narrower scope for that specific step.

Segments each case using `mu0` (self-heal probability) and τ together:
`sleeping_dog` (τ < {SLEEPING_DOG_UPLIFT}) → `sure_thing` (mu0 ≥ {SURE_THING_BASELINE}) →
`lost_cause` (τ ≤ {LOST_CAUSE_UPLIFT}) → else `persuadable`.

## Data
{metrics["n_train"]} train / {metrics["n_val"]} val / {metrics["n_test"]} test cases
(seed {metrics["train_seed"]}), stratified by cohort, outcomes bootstrapped exactly
as in `ml/cards/propensity.md`.

## Metrics (held-out test set)
- **Qini coefficient: {metrics["qini_coefficient"]:.4f}** (gate: > 0) — model targeting
  beats random targeting by this much cumulative incremental recovery.
- **Uplift at top 20%:** {metrics["uplift_at_top20pct"]:.4f} — the incremental recovery
  rate the model would capture by only acting on its top-scored fifth of cases.
- **Agreement with the generator's ground-truth τ (Spearman): {metrics["ground_truth_spearman"]:.4f}**
  — the *only* place ground truth is used post-training: validating that the
  model's ranking resembles the true, unobservable-in-production uplift.
- Qini curve: `ml/artifacts/uplift/qini_curve.png`

## Segment distribution (test set)
| Segment | Count |
|---|---|
{segments}

## Known failure modes
- **X-learner, not a causal forest.** ADR-0007's explicit tradeoff: this is
  transparent and fast to train, but less robust to complex treatment-effect
  heterogeneity than a causal forest would be. The fallback if this had proven
  unstable was a documented heuristic (treated propensity minus self-heal prior),
  never shipped as if it were a trained model — it wasn't needed here.
- **Channel-agnostic by construction** (see `ml/cards/propensity.md`'s note on the
  same tradeoff) — this τ is "does acting at all help", not "does acting via
  channel X help"; channel selection is the bandit's job (Phase 06).
- **The Spearman agreement number is a validation diagnostic, not a training
  signal** — ground truth never entered any `.fit()` call in this script, only
  the final correlation check. A future reader should not expect this number in
  production, where no such ground truth will exist to check against.
- **Same cold-start and bootstrapped-outcome limitations as the propensity models.**
"""
    CARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    CARD_PATH.write_text(card, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
