"""Turns a generated case's hidden ground truth into a single, seeded
resolution outcome for the measurement engine (Phase 10).

This is the one place `GroundTruth.p_self_heal`/`p_recover_by_channel`
(data/generate.py -- "never available as features at inference") is read
back after generation. It backs the *measured* headline number, not any
model: a control case (or a treated case nothing was ever sent to) resolves
against `p_self_heal` alone; a treated case that was actually sent a message
resolves against `p_recover_by_channel[channel]` -- the channel of its last
successful send, since the generator defines that probability as already
"whatever bump this channel gives over self-heal", not an independent
per-attempt hazard to be composed across a multi-step ladder (composing it
would double-count and inflate resolution far past what the generator
intended). Exactly one roll per case, deterministic from `(seed, case_id)`
alone -- independent of processing order, so a batch run in any order or
concurrency produces the same outcome for the same case every time.
"""

from __future__ import annotations

import random

from recoup.data.generate import GroundTruth


def resolution_probability(ground_truth: GroundTruth, contacted_channel: str | None) -> float:
    if contacted_channel is not None:
        return ground_truth.p_recover_by_channel[contacted_channel]
    return ground_truth.p_self_heal


def simulate_resolved(*, case_id: str, seed: int, probability: float) -> bool:
    rng = random.Random(f"gt-resolution:{seed}:{case_id}")
    return rng.random() < probability
