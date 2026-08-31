"""Qini curve and Qini coefficient for uplift evaluation (FR-3.5).

Standard formulation (Radcliffe 2007): sort held-out cases by predicted uplift,
descending. At the top-k fraction, g(k) = Y_t(k) - Y_c(k) * (N_t(k)/N_c(k)) — the
treated positives in the top-k, minus the control positives in the top-k rescaled
to what they'd be if the arms were equal-sized. The Qini coefficient is the area
between that curve and the "random targeting" diagonal; positive means the model
finds real incremental value, not just correlation with outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class QiniCurve:
    fractions: list[float]
    gains: list[float]
    qini_coefficient: float


def compute_qini_curve(
    outcome: NDArray[np.int_],
    is_treated: NDArray[np.bool_],
    uplift_score: NDArray[np.float64],
    steps: int = 20,
) -> QiniCurve:
    order = np.argsort(-uplift_score)
    y = outcome[order]
    t = is_treated[order]
    n = len(y)

    fractions = [0.0, *[step / steps for step in range(1, steps + 1)]]
    gains = [0.0]
    for frac in fractions[1:]:
        k = max(round(frac * n), 1)
        y_top, t_top = y[:k], t[:k]
        n_t = max(int(t_top.sum()), 1)
        n_c = max(int((~t_top).sum()), 1)
        y_t = int(y_top[t_top].sum())
        y_c = int(y_top[~t_top].sum())
        gains.append(y_t - y_c * (n_t / n_c))

    model_area = float(np.trapezoid(gains, fractions))
    random_area = 0.5 * gains[-1] * fractions[-1]
    qini_coefficient = model_area - random_area
    return QiniCurve(fractions=fractions, gains=gains, qini_coefficient=qini_coefficient)


def uplift_at_k(
    outcome: NDArray[np.int_],
    is_treated: NDArray[np.bool_],
    uplift_score: NDArray[np.float64],
    k: float,
) -> float:
    """Incremental recovery rate in the top-k fraction, model-targeted vs the rest."""
    order = np.argsort(-uplift_score)
    y, t = outcome[order], is_treated[order]
    n = len(y)
    cut = max(round(k * n), 1)
    top_y, top_t = y[:cut], t[:cut]
    rate_t = top_y[top_t].mean() if top_t.any() else 0.0
    rate_c = top_y[~top_t].mean() if (~top_t).any() else 0.0
    return float(rate_t - rate_c)
