"""FR-11.5: the 62-utterance Hinglish/English PTP golden set, evaluated
against the live model. Precision, recall, and false-positive rate are
reported *separately* — a false positive (the model confidently believing
a promise was made when it wasn't) is the dangerous error class: it would
silently suspend escalation on a case nobody actually promised anything on.
Gated on a live `ANTHROPIC_API_KEY`, same as `tests/llm_eval`'s other suites.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from recoup.llm.ptp import extract_ptp
from recoup.settings import get_settings
from recoup.voice.runtime import PTP_CONFIDENCE_THRESHOLD

pytestmark = [
    pytest.mark.llm_eval,
    pytest.mark.skipif(
        not get_settings().anthropic_api_key, reason="no ANTHROPIC_API_KEY configured"
    ),
]

_GOLDEN_PATH = Path(__file__).parent / "ptp_golden.jsonl"
_REFERENCE_NOW = datetime(
    2026, 1, 5, tzinfo=UTC
)  # "today" all relative-date entries resolve against

# Bars a real, working extractor should clear. FPR is capped much tighter
# than the miss rate is — a missed promise costs a follow-up message; a
# fabricated one costs the customer's trust in a system that "remembers"
# something they never said.
_MIN_PRECISION = 0.70
_MIN_RECALL = 0.60
_MAX_FALSE_POSITIVE_RATE = 0.15


@dataclass(frozen=True)
class GoldenCase:
    utterance: str
    expected_accept: bool  # would a correct extractor auto-accept this as a real PTP?
    category: str


def _load_golden_set() -> list[GoldenCase]:
    cases = []
    with _GOLDEN_PATH.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            expected_accept = bool(row["expected_has_commitment"]) and bool(
                row["expected_high_confidence"]
            )
            cases.append(
                GoldenCase(
                    utterance=row["utterance"],
                    expected_accept=expected_accept,
                    category=row["category"],
                )
            )
    return cases


async def test_ptp_extraction_precision_recall_and_false_positive_rate() -> None:
    cases = _load_golden_set()
    assert len(cases) >= 60, "golden set must have at least 60 labelled utterances (FR-11.5)"

    true_positives = false_positives = true_negatives = false_negatives = 0
    misses: list[str] = []
    fabrications: list[str] = []

    for case in cases:
        extraction = await extract_ptp(case.utterance, _REFERENCE_NOW)
        accepted = (
            extraction is not None
            and extraction.has_commitment
            and extraction.confidence >= PTP_CONFIDENCE_THRESHOLD
        )
        if accepted and case.expected_accept:
            true_positives += 1
        elif accepted and not case.expected_accept:
            false_positives += 1
            fabrications.append(case.utterance)
        elif not accepted and case.expected_accept:
            false_negatives += 1
            misses.append(case.utterance)
        else:
            true_negatives += 1

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives)
        else 1.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives)
        else 1.0
    )
    false_positive_rate = (
        false_positives / (false_positives + true_negatives)
        if (false_positives + true_negatives)
        else 0.0
    )

    report = (
        f"precision={precision:.2f} recall={recall:.2f} FPR={false_positive_rate:.2f} "
        f"(tp={true_positives} fp={false_positives} tn={true_negatives} fn={false_negatives})\n"
        f"fabricated PTPs (dangerous): {fabrications}\n"
        f"missed PTPs: {misses}"
    )

    assert false_positive_rate <= _MAX_FALSE_POSITIVE_RATE, report
    assert precision >= _MIN_PRECISION, report
    assert recall >= _MIN_RECALL, report
