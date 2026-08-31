"""Unit tests for the individual rule functions in policy/rules/."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from recoup.policy.rules.consent import has_consent
from recoup.policy.rules.mandate import (
    exceeds_cadence_cap,
    is_never_retry_cause,
    requires_additional_authentication,
    requires_pre_debit_notice,
    violates_minimum_gap,
)
from recoup.policy.rules.opt_out import blocks_contact

pytestmark = pytest.mark.unit


def test_has_consent_true_when_channel_is_in_the_recorded_set() -> None:
    assert has_consent("sms", frozenset({"sms", "email"})) is True


def test_has_consent_false_when_channel_has_no_recorded_consent() -> None:
    assert has_consent("voice", frozenset({"sms", "email"})) is False


def test_has_consent_true_when_no_channel_is_involved() -> None:
    assert has_consent(None, frozenset()) is True


def test_blocks_contact_mirrors_the_opted_out_flag() -> None:
    assert blocks_contact(True) is True
    assert blocks_contact(False) is False


def test_is_never_retry_cause() -> None:
    never_retry = ["mandate_revoked", "mandate_insufficient_balance"]
    assert is_never_retry_cause("mandate_revoked", never_retry) is True
    assert is_never_retry_cause("mandate_technical_failure", never_retry) is False
    assert is_never_retry_cause(None, never_retry) is False


def test_exceeds_cadence_cap() -> None:
    assert exceeds_cadence_cap(3, max_per_cycle=3) is True
    assert exceeds_cadence_cap(2, max_per_cycle=3) is False


def test_violates_minimum_gap_true_when_the_last_retry_was_too_recent() -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    last_retry = now - timedelta(hours=2)
    assert violates_minimum_gap(last_retry, now, timedelta(days=1)) is True


def test_violates_minimum_gap_false_once_enough_time_has_passed() -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    last_retry = now - timedelta(days=2)
    assert violates_minimum_gap(last_retry, now, timedelta(days=1)) is False


def test_violates_minimum_gap_false_with_no_prior_retry() -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    assert violates_minimum_gap(None, now, timedelta(days=1)) is False


def test_requires_pre_debit_notice() -> None:
    assert requires_pre_debit_notice(required=True, already_sent=False) is True
    assert requires_pre_debit_notice(required=True, already_sent=True) is False
    assert requires_pre_debit_notice(required=False, already_sent=False) is False


def test_requires_additional_authentication_above_the_afa_threshold() -> None:
    assert requires_additional_authentication(Decimal("20000"), Decimal("15000")) is True
    assert requires_additional_authentication(Decimal("15000"), Decimal("15000")) is True
    assert requires_additional_authentication(Decimal("1000"), Decimal("15000")) is False
