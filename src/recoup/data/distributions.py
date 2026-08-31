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
    "voice": 1.15,
    "whatsapp": 1.05,
    "sms": 0.90,
    "email": 0.70,
}

# Uplift segments (see the domain glossary) and their share of a batch.
UPLIFT_ARCHETYPES: WeightedChoices = [
    ("persuadable", 0.50),
    ("sure_thing", 0.20),
    ("lost_cause", 0.20),
    ("sleeping_dog", 0.10),
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
