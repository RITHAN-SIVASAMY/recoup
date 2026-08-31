"""Train the FR-2 root-cause classifier.

Scope, honestly stated: this classifies `payment_failure` and `mandate_failure`
cases into the nine diagnosable causes in `ROOT_CAUSE_TAXONOMY`. It does *not*
classify `checkout_abandonment` or `receivable_overdue` — source_type already
determines those with certainty, and folding two trivially-easy classes into the
reported macro-F1 would inflate the number without the model having done anything
Root-cause diagnosis. That would violate "no model output bypasses calibration"
in spirit even if not in letter: the number would look strong for the wrong reason.

Run: `uv run python ml/train_classifier.py` (also behind `make train`).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import joblib
import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import CATEGORICAL_COLUMNS, FEATURE_COLUMNS, build_feature_frame

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from recoup.data.distributions import ROOT_CAUSE_TAXONOMY
from recoup.data.generate import generate_batch
from recoup.understanding.calibration import MulticlassCalibrator, multiclass_brier_score

TRAIN_SEED = 20260301  # distinct from the demo batch's seed=42; a large synthetic pool
N_CASES = 12000
ARTIFACT_DIR = Path("ml/artifacts/classifier")
CARD_PATH = Path("ml/cards/classifier.md")
CLASS_LABELS = list(ROOT_CAUSE_TAXONOMY)


def _content_hash(*parts: bytes) -> str:
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(part)
    return hasher.hexdigest()[:16]


def _split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # Each synthetic case has a unique customer_ref, so a row-level stratified split
    # and a customer-grouped split coincide here. Revisit with a GroupShuffleSplit
    # if/when repeat-customer modeling makes that no longer true.
    train, temp = train_test_split(
        frame, test_size=0.30, stratify=frame["true_root_cause"], random_state=TRAIN_SEED
    )
    val, test = train_test_split(
        temp, test_size=0.50, stratify=temp["true_root_cause"], random_state=TRAIN_SEED
    )
    return train, val, test


def _plot_confusion_matrix(cm: np.ndarray, labels: list[str], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Root-cause classifier — confusion matrix (test set)")
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center", fontsize=6)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_reliability_curve(confidences: np.ndarray, correct: np.ndarray, path: Path) -> None:
    bins = np.linspace(0.0, 1.0, 11)
    bin_indices = np.digitize(confidences, bins) - 1
    bin_indices = np.clip(bin_indices, 0, len(bins) - 2)
    xs, ys, counts = [], [], []
    for b in range(len(bins) - 1):
        mask = bin_indices == b
        if mask.sum() == 0:
            continue
        xs.append(confidences[mask].mean())
        ys.append(correct[mask].mean())
        counts.append(int(mask.sum()))

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "k--", label="perfectly calibrated")
    ax.plot(xs, ys, "o-", label="classifier (top-1 confidence)")
    for x, y, n in zip(xs, ys, counts, strict=True):
        ax.annotate(f"n={n}", (x, y), fontsize=7, textcoords="offset points", xytext=(4, 4))
    ax.set_xlabel("Predicted confidence")
    ax.set_ylabel("Empirical accuracy")
    ax.set_title("Root-cause classifier — reliability curve")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    CARD_PATH.parent.mkdir(parents=True, exist_ok=True)

    batch = generate_batch(seed=TRAIN_SEED, n_cases=N_CASES)
    frame = build_feature_frame(batch)
    frame = frame[frame["source_type"].isin(["payment_failure", "mandate_failure"])].copy()
    for col in CATEGORICAL_COLUMNS:
        frame[col] = frame[col].cat.remove_unused_categories()

    train, val, test = _split(frame)

    model = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=len(CLASS_LABELS),
        n_estimators=350,
        learning_rate=0.06,
        num_leaves=31,
        min_child_samples=15,
        random_state=TRAIN_SEED,
        verbosity=-1,
    )
    model.fit(train[FEATURE_COLUMNS], train["true_root_cause"])
    # LightGBM/sklearn sorts classes_ alphabetically at fit time — not the
    # declaration order of ROOT_CAUSE_TAXONOMY. Every downstream array is indexed
    # by *this* order, or probability column k silently means the wrong class.
    class_labels = list(model.classes_)

    val_proba_raw = model.predict_proba(val[FEATURE_COLUMNS])
    calibrator = MulticlassCalibrator.fit(
        val_proba_raw, val["true_root_cause"].to_numpy(), class_labels
    )

    test_proba_raw = model.predict_proba(test[FEATURE_COLUMNS])
    test_proba = calibrator.transform(test_proba_raw)
    y_test = test["true_root_cause"].to_numpy()
    y_pred = np.array(class_labels)[test_proba.argmax(axis=1)]

    macro_f1 = f1_score(y_test, y_pred, average="macro", labels=class_labels)
    brier = multiclass_brier_score(test_proba, y_test, class_labels)
    cm = confusion_matrix(y_test, y_pred, labels=class_labels)
    report = classification_report(
        y_test, y_pred, labels=class_labels, output_dict=True, zero_division=0
    )

    confidences = test_proba.max(axis=1)
    correct = (y_pred == y_test).astype(float)

    _plot_confusion_matrix(cm, class_labels, ARTIFACT_DIR / "confusion_matrix.png")
    _plot_reliability_curve(confidences, correct, ARTIFACT_DIR / "reliability_curve.png")

    explainer = shap.TreeExplainer(model)
    sample = test[FEATURE_COLUMNS].sample(n=min(300, len(test)), random_state=TRAIN_SEED)
    shap_values = explainer.shap_values(sample)
    # shap_values: list[len=n_classes] of (n_samples, n_features), or a 3D array
    # depending on the shap version — normalize to the list form before averaging.
    if isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
        shap_values = [shap_values[:, :, k] for k in range(shap_values.shape[2])]
    mean_abs_shap = np.mean([np.abs(sv).mean(axis=0) for sv in shap_values], axis=0)
    shap_summary = dict(
        sorted(
            zip(FEATURE_COLUMNS, (float(v) for v in mean_abs_shap), strict=True),
            key=lambda kv: kv[1],
            reverse=True,
        )
    )

    joblib.dump(model, ARTIFACT_DIR / "model.joblib")
    joblib.dump(calibrator, ARTIFACT_DIR / "calibrator.joblib")
    model_version = _content_hash(
        Path(ARTIFACT_DIR / "model.joblib").read_bytes(), str(TRAIN_SEED).encode()
    )

    metrics = {
        "model_version": f"classifier-{model_version}",
        "train_seed": TRAIN_SEED,
        "n_cases_generated": N_CASES,
        "n_train": len(train),
        "n_val": len(val),
        "n_test": len(test),
        "class_labels": class_labels,
        "macro_f1": macro_f1,
        "brier_score": brier,
        "confusion_matrix": cm.tolist(),
        "per_class_report": report,
        "shap_mean_abs": shap_summary,
        "gate": {"macro_f1_min": 0.85, "brier_max": 0.12},
        "gate_passed": bool(macro_f1 >= 0.85 and brier <= 0.12),
    }
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    _write_model_card(metrics, report)

    print(f"macro-F1: {macro_f1:.4f} (gate >= 0.85)")
    print(f"Brier:    {brier:.4f} (gate <= 0.12)")
    print(f"model_version: {metrics['model_version']}")
    return 0 if metrics["gate_passed"] else 1


def _write_model_card(metrics: dict, report: dict) -> None:  # type: ignore[type-arg]
    rows = "\n".join(
        f"| {label} | {report[label]['precision']:.2f} | {report[label]['recall']:.2f} "
        f"| {report[label]['f1-score']:.2f} | {int(report[label]['support'])} |"
        for label in metrics["class_labels"]
    )
    top_features = "\n".join(
        f"| {feature} | {value:.4f} |"
        for feature, value in list(metrics["shap_mean_abs"].items())[:6]
    )
    card = f"""# Model card — root-cause classifier

## What it does
Classifies `payment_failure` and `mandate_failure` cases into one of nine causes
(`{", ".join(metrics["class_labels"])}`). `checkout_abandonment` and
`receivable_overdue` are read directly off `source_type`, not classified — see
`ml/train_classifier.py`'s module docstring for why folding those in would be
dishonest about what the model is actually doing.

## Data
{metrics["n_cases_generated"]} synthetic cases (seed {metrics["train_seed"]}), filtered to
payment/mandate failures, stratified 70/15/15 into {metrics["n_train"]} train /
{metrics["n_val"]} calibration / {metrics["n_test"]} test cases. Every synthetic
customer is unique, so a row-level and a customer-grouped split coincide here — see
the note in `ml/train_classifier.py::_split`.

## Metrics (held-out test set)
- **macro-F1: {metrics["macro_f1"]:.4f}** (gate: ≥ 0.85)
- **Brier score: {metrics["brier_score"]:.4f}** (gate: ≤ 0.12, isotonic-calibrated one-vs-rest)
- Confusion matrix: `ml/artifacts/classifier/confusion_matrix.png`
- Reliability curve: `ml/artifacts/classifier/reliability_curve.png`

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
{rows}

## Feature attribution (mean absolute SHAP, top 6)
| Feature | Mean \\|SHAP\\| |
|---|---|
{top_features}

## Known failure modes
- **Irreducible label noise, by construction.** The generator resamples ~8% of
  labels to a confusable alternate (e.g. a `bank_declined` code is sometimes truly
  an `issuer_risk_block`) to avoid a classifier that's just a lookup table wearing
  a model's clothes — see `CONFUSION_PROBABILITY` in `data/distributions.py`. That
  noise puts a real ceiling on achievable macro-F1 well below 1.0; the number above
  is not being compared against a clean-label upper bound.
- **`network_or_gateway_error` is the smallest class** by construction (~5% of
  payment failures) and is the class most likely to have the widest confidence
  interval on its per-class F1; treat that row as the least trustworthy in isolation.
- **No customer-history features.** FR-2.2 lists prior-attempt features and
  customer history as candidate inputs; this synthetic batch has no repeat
  customers, so every case is effectively `cold_start` (FR-2.7) and the model has
  never had the chance to learn from repeat behavior. That's a real, not cosmetic,
  gap versus the FRD's stated feature set.
- **Mandate signal is thin.** `consecutive_failures` and `status` are the only
  mandate-side features; a real e-mandate failure carries considerably more
  structured detail (issuer NPCI response codes) that this synthetic batch does
  not model.
- **What would fix it:** real (or richer synthetic) customer-history features,
  and a larger, independently-sourced confusion matrix for the decline-reason →
  root-cause mapping instead of the documented assumption in `data/distributions.py`.
"""
    CARD_PATH.write_text(card, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
