"""FR-11.1: the PTP extraction schema and the no-key degradation path — the
live-model extraction quality itself is proven by tests/llm_eval/test_ptp_golden.py
(gated on a real API key), matching how llm/client.py's drafting is proven.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from recoup.llm.ptp import extract_ptp
from recoup.llm.schemas import PTPExtraction
from recoup.settings import get_settings

pytestmark = pytest.mark.unit


async def test_extract_ptp_degrades_to_none_with_no_api_key_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "", raising=False)
    result = await extract_ptp("main Friday tak pay kar dunga", datetime.now(UTC))
    assert result is None


def test_ptp_extraction_accepts_a_well_formed_commitment() -> None:
    extraction = PTPExtraction(
        has_commitment=True,
        amount_inr="499.00",  # type: ignore[arg-type]
        promised_date="2026-09-05",  # type: ignore[arg-type]
        condition=None,
        confidence=0.9,
    )
    assert extraction.has_commitment is True
    assert extraction.confidence == 0.9


def test_ptp_extraction_accepts_no_commitment_at_all() -> None:
    extraction = PTPExtraction(has_commitment=False, confidence=0.95)
    assert extraction.amount_inr is None
    assert extraction.promised_date is None


def test_ptp_extraction_rejects_a_confidence_outside_0_1() -> None:
    with pytest.raises(ValidationError):
        PTPExtraction(has_commitment=True, confidence=1.5)


def test_ptp_extraction_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PTPExtraction.model_validate(
            {"has_commitment": False, "confidence": 0.5, "unexpected_field": "x"}
        )
