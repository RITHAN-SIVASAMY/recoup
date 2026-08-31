"""One-vs-rest isotonic calibration, shared by training and inference.

Lives in the runtime package, not `ml/`, for a concrete reason: `joblib.dump` on a
`MulticlassCalibrator` records its class under this exact module path, and
`joblib.load` at inference time needs that same path importable — which it isn't
if the class is defined in a bare top-level `ml/calibration.py` script that's
never installed. `ml/train_classifier.py` and `ml/train_propensity.py` import
from here rather than redefining it, so the pickled artifact and the code that
loads it always agree.

`sklearn.calibration.CalibratedClassifierCV`'s `cv="prefit"` path has also shifted
across sklearn versions; a hand-rolled per-class isotonic fit has no such version
sensitivity, and is exactly what a reader can audit — which matters more here than
convenience, since the EV engine downstream consumes these numbers as real
probabilities (CLAUDE.md rule: no model output bypasses calibration).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sklearn.isotonic import IsotonicRegression


@dataclass
class MulticlassCalibrator:
    """One IsotonicRegression per class, fit one-vs-rest, then renormalized to sum to 1."""

    class_labels: list[str]
    _calibrators: list[IsotonicRegression]

    @classmethod
    def fit(
        cls, raw_proba: NDArray[np.float64], y_true: NDArray[np.str_], class_labels: list[str]
    ) -> MulticlassCalibrator:
        calibrators = []
        for k, label in enumerate(class_labels):
            target = (y_true == label).astype(float)
            calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            calibrator.fit(raw_proba[:, k], target)
            calibrators.append(calibrator)
        return cls(class_labels=class_labels, _calibrators=calibrators)

    def transform(self, raw_proba: NDArray[np.float64]) -> NDArray[np.float64]:
        calibrated = np.column_stack(
            [calibrator.predict(raw_proba[:, k]) for k, calibrator in enumerate(self._calibrators)]
        )
        row_sums = calibrated.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        result: NDArray[np.float64] = calibrated / row_sums
        return result


def binary_calibrator(
    raw_proba: NDArray[np.float64], y_true: NDArray[np.float64]
) -> IsotonicRegression:
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(raw_proba, y_true)
    return calibrator


def multiclass_brier_score(
    calibrated_proba: NDArray[np.float64], y_true: NDArray[np.str_], class_labels: list[str]
) -> float:
    """Mean per-class squared error between the predicted simplex and the one-hot truth.

    Averaged over classes (divided by K), not just summed — the sum-over-classes
    convention (Brier's original 1950 multi-category formula) ranges over [0, 2]
    and does *not* reduce to the familiar binary Brier score at K=2: summing both
    the positive- and negative-class terms double-counts what `sklearn.metrics.
    brier_score_loss` reports as a single number. Dividing by K makes this formula
    agree with the standard binary Brier score exactly when K=2, which is the
    convention `docs/05-EVALUATION-PROTOCOL.md`'s "Brier <= 0.12" gate assumes —
    that threshold is a well-known binary-Brier benchmark value, not a [0, 2]-range one.
    """
    one_hot = np.array([[1.0 if label == y else 0.0 for label in class_labels] for y in y_true])
    return float(np.mean(np.sum((calibrated_proba - one_hot) ** 2, axis=1)) / len(class_labels))
