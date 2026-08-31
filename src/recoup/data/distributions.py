"""Documented synthetic-data modeling assumptions.

These are illustrative distributions chosen to be *plausible* for the Indian
payments context the FRD describes — not measurements from a real dataset.
`docs/05-EVALUATION-PROTOCOL.md` names "synthetic data flatters the models" as a
threat to validity for exactly this reason, which is why every distribution here
is spelled out and weighted explicitly rather than buried in code: a reader should
be able to see, and challenge, every assumption this generator makes.
"""

from __future__ import annotations

import random

WeightedChoices = list[tuple[str, float]]

DECLINE_REASONS: WeightedChoices = [
    ("insufficient_funds", 0.30),
    ("bank_declined", 0.20),
    ("otp_timeout", 0.15),
    ("risk_declined", 0.10),
    ("card_expired", 0.08),
    ("invalid_card", 0.07),
    ("processing_error", 0.05),
    ("daily_limit_exceeded", 0.05),
]

ISSUERS: WeightedChoices = [
    ("HDFC Bank", 0.20),
    ("ICICI Bank", 0.18),
    ("State Bank of India", 0.17),
    ("Axis Bank", 0.13),
    ("Kotak Mahindra Bank", 0.10),
    ("Punjab National Bank", 0.09),
    ("Bank of Baroda", 0.08),
    ("IDFC FIRST Bank", 0.05),
]

# UPI dominates online payment volume in India; this ordering (not the exact split)
# is the load-bearing assumption.
PAYMENT_METHODS: WeightedChoices = [
    ("upi", 0.55),
    ("card", 0.25),
    ("netbanking", 0.15),
    ("wallet", 0.05),
]

CHANNELS: tuple[str, ...] = ("sms", "whatsapp", "email", "voice")

# Relative effectiveness multiplier per channel, applied to a persuadable case's
# uplift — a documented ordering (voice > WhatsApp > SMS > email), not a measurement.
CHANNEL_EFFECTIVENESS: dict[str, float] = {
    "voice": 1.40,
    "whatsapp": 1.10,
    "sms": 0.75,
    "email": 0.35,
}

# Uplift segments (see the domain glossary) and their share of a batch.
UPLIFT_ARCHETYPES: WeightedChoices = [
    ("persuadable", 0.50),
    ("sure_thing", 0.20),
    ("lost_cause", 0.20),
    ("sleeping_dog", 0.10),
]

# FR-2.1's decline taxonomy — what the Phase 03 classifier predicts. "unknown" is
# not trained toward; it's an inference-time abstention below a confidence floor
# (FR-2.6), and checkout_abandonment/receivable_overdue are read straight off
# source_type rather than classified — see ml/train_classifier.py's docstring for why.
ROOT_CAUSE_TAXONOMY: tuple[str, ...] = (
    "bank_soft_decline",
    "insufficient_funds",
    "otp_timeout_or_auth_abandon",
    "network_or_gateway_error",
    "issuer_risk_block",
    "card_expired_or_invalid",
    "mandate_revoked",
    "mandate_insufficient_balance",
    "mandate_technical_failure",
)

# The raw decline_reason a (synthetic) gateway returns is real signal but not a
# perfect one — real decline codes are genuinely ambiguous between a few causes.
# Each entry: (primary root cause, confusable alternates). With probability
# CONFUSION_PROBABILITY the true label is resampled uniformly from the alternates
# instead of the primary — irreducible label noise a classifier cannot learn its
# way around, which is the honest reason macro-F1 has a ceiling below 1.0.
DECLINE_REASON_ROOT_CAUSE: dict[str, tuple[str, list[str]]] = {
    "insufficient_funds": ("insufficient_funds", ["bank_soft_decline"]),
    "bank_declined": ("bank_soft_decline", ["issuer_risk_block", "network_or_gateway_error"]),
    "otp_timeout": ("otp_timeout_or_auth_abandon", ["network_or_gateway_error"]),
    "risk_declined": ("issuer_risk_block", ["bank_soft_decline"]),
    "card_expired": ("card_expired_or_invalid", []),
    "invalid_card": ("card_expired_or_invalid", []),
    "processing_error": ("network_or_gateway_error", ["bank_soft_decline"]),
    "daily_limit_exceeded": ("bank_soft_decline", ["insufficient_funds"]),
}
CONFUSION_PROBABILITY = 0.08

# Mandate failures: real Razorpay subscription statuses (halted, cancelled, ...)
# don't map 1:1 onto our finer root-cause taxonomy either — consecutive_failures
# is a genuine, weakly-correlated observable signal, not a leak of the true cause.
MANDATE_ROOT_CAUSE_WEIGHTS: WeightedChoices = [
    ("mandate_technical_failure", 0.40),
    ("mandate_insufficient_balance", 0.35),
    ("mandate_revoked", 0.25),
]

# Salary-cycle effect: revenue-at-risk events cluster in the days just before and
# just after a typical Indian salary date (last few days of the month, and the 1st).
SALARY_CYCLE_DAY_WEIGHTS: dict[int, float] = {
    **dict.fromkeys((28, 29, 30, 31, 1, 2, 3), 1.6),
    **dict.fromkeys(range(10, 21), 0.7),  # mid-month lull
}
_DEFAULT_DAY_WEIGHT = 1.0

# Time-of-day effect: online shopping and bill-checking cluster in the evening.
HOUR_OF_DAY_WEIGHTS: dict[int, float] = {
    **dict.fromkeys(range(19, 23), 1.8),  # 7pm-11pm
    **dict.fromkeys(range(1, 6), 0.4),  # small hours
}
_DEFAULT_HOUR_WEIGHT = 1.0


def weighted_choice(rng: random.Random, choices: WeightedChoices) -> str:
    labels = [label for label, _ in choices]
    weights = [weight for _, weight in choices]
    return rng.choices(labels, weights=weights, k=1)[0]


def day_of_month_weight(day: int) -> float:
    return SALARY_CYCLE_DAY_WEIGHTS.get(day, _DEFAULT_DAY_WEIGHT)


def hour_of_day_weight(hour: int) -> float:
    return HOUR_OF_DAY_WEIGHTS.get(hour, _DEFAULT_HOUR_WEIGHT)


def noisy_root_cause_for_decline(rng: random.Random, decline_reason: str) -> str:
    primary, alternates = DECLINE_REASON_ROOT_CAUSE[decline_reason]
    if alternates and rng.random() < CONFUSION_PROBABILITY:
        return rng.choice(alternates)
    return primary


def mandate_root_cause(rng: random.Random) -> str:
    return weighted_choice(rng, MANDATE_ROOT_CAUSE_WEIGHTS)


# Payment-failure decline reasons that tend to resolve themselves versus ones that
# structurally need an outside fix — a documented tilt, not a measurement. Applied
# on top of, not instead of, the source_type and amount effects below.
_DECLINE_REASON_ARCHETYPE_TILT: dict[str, str] = {
    "insufficient_funds": "sure_thing",  # salary lands, balance clears on its own
    "otp_timeout": "sure_thing",  # the customer just retries
    "processing_error": "sure_thing",  # transient; often works next attempt
    "daily_limit_exceeded": "sure_thing",  # resets the next day regardless
    "bank_declined": "persuadable",
    "card_expired": "persuadable",  # needs a new card, but will act if nudged
    "invalid_card": "persuadable",
    "risk_declined": "lost_cause",  # needs the issuer's own risk review, not a nudge
}
_TILT_STRENGTH = 6.0


def archetype_weights_for(
    source_type: str, relative_amount: float, decline_reason: str | None = None
) -> WeightedChoices:
    """Uplift-archetype weights, shifted by observable features.

    `relative_amount` is amount_at_risk's position within its merchant profile's
    range, 0..1. Without a dependency like this on something a model can actually
    see, a propensity/uplift model trained on features could never beat random
    guessing — the archetype (and therefore p_self_heal) would be pure noise
    relative to every column in the feature frame. These specific shifts are
    documented assumptions, not measurements: checkout abandonment self-heals
    more often (the customer was just distracted); mandate failures are stickier
    (a lapsed or revoked mandate rarely fixes itself); higher-value cases lean
    more persuadable (there's more reason for both sides to engage).
    """
    weights = dict(UPLIFT_ARCHETYPES)

    if source_type == "checkout_abandonment":
        weights["sure_thing"] *= 9.0
        weights["lost_cause"] *= 0.15
        weights["persuadable"] *= 0.4
    elif source_type == "mandate_failure":
        weights["lost_cause"] *= 4.5
        weights["sleeping_dog"] *= 5.0
        weights["sure_thing"] *= 0.08
        weights["persuadable"] *= 0.35
    elif source_type == "receivable_overdue":
        weights["persuadable"] *= 3.5
        weights["sleeping_dog"] *= 0.2
        weights["sure_thing"] *= 0.35

    if decline_reason is not None:
        tilt = _DECLINE_REASON_ARCHETYPE_TILT.get(decline_reason)
        if tilt is not None:
            weights[tilt] *= _TILT_STRENGTH

    weights["persuadable"] *= 0.25 + 2.5 * relative_amount
    weights["sure_thing"] *= 1.6 - 1.2 * relative_amount
    weights["lost_cause"] *= 2.2 - 1.8 * relative_amount

    total = sum(weights.values())
    return [(label, weight / total) for label, weight in weights.items()]
