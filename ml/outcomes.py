"""Bootstrap treatment/control outcomes from the generator's ground-truth curves.

This is the only place `p_self_heal`/`p_recover_by_channel` are used for anything
beyond validation — and even here, they never reach a trained model directly.
Realizing a stochastic Bernoulli outcome per case is legitimate simulation
methodology (ADR-0007: "bootstrapped from the synthetic generator's ground-truth
response curves"), standing in for the real historical treatment/control outcomes
this system will accumulate once it's live. The propensity models below are
trained on the realized 0/1 `recovered` column, exactly as they would be on real
data — never on the probabilities themselves.
"""

from __future__ import annotations

import random

import pandas as pd


def realize_outcomes(frame: pd.DataFrame, *, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    cohorts: list[str] = []
    channels: list[str | None] = []
    recovered: list[int] = []

    for _, row in frame.iterrows():
        if rng.random() < 0.5:
            cohorts.append("control")
            channels.append(None)
            recovered.append(1 if rng.random() < row["p_self_heal"] else 0)
        else:
            cohorts.append("treatment")
            channel_probs: dict[str, float] = row["p_recover_by_channel"]
            channel = rng.choice(list(channel_probs.keys()))
            channels.append(channel)
            recovered.append(1 if rng.random() < channel_probs[channel] else 0)

    result = frame.copy()
    result["cohort"] = cohorts
    result["channel"] = channels
    result["recovered"] = recovered
    return result
