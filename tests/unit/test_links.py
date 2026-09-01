"""SEC-DATA-04: HMAC-signed, expiring recovery link tokens — pure signing
and verification, no I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from recoup.execution.links import generate_link_token, verify_link_token

pytestmark = pytest.mark.unit

_SECRET = "test-signing-secret"
_NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def test_a_freshly_generated_token_verifies() -> None:
    token = generate_link_token(
        "01ARZ3NDEKTSV4RRFFQ69G5FAV", 1, secret=_SECRET, ttl=timedelta(hours=72), now=_NOW
    )
    payload = verify_link_token(token, secret=_SECRET, now=_NOW)
    assert payload is not None
    assert payload.case_id == "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    assert payload.ladder_step == 1


def test_a_token_signed_with_a_different_secret_never_verifies() -> None:
    token = generate_link_token(
        "01ARZ3NDEKTSV4RRFFQ69G5FAV", 1, secret=_SECRET, ttl=timedelta(hours=72), now=_NOW
    )
    assert verify_link_token(token, secret="a-different-secret", now=_NOW) is None


def test_an_expired_token_never_verifies() -> None:
    token = generate_link_token(
        "01ARZ3NDEKTSV4RRFFQ69G5FAV", 1, secret=_SECRET, ttl=timedelta(hours=72), now=_NOW
    )
    past_expiry = _NOW + timedelta(hours=73)
    assert verify_link_token(token, secret=_SECRET, now=past_expiry) is None


def test_a_token_at_the_exact_expiry_instant_is_treated_as_expired() -> None:
    token = generate_link_token(
        "01ARZ3NDEKTSV4RRFFQ69G5FAV", 1, secret=_SECRET, ttl=timedelta(hours=72), now=_NOW
    )
    exact_expiry = _NOW + timedelta(hours=72)
    assert verify_link_token(token, secret=_SECRET, now=exact_expiry) is None


@pytest.mark.parametrize(
    "garbage",
    ["", "not-a-token", "missing-dot-signature", "a.b.c", "🎉.notvalidb64!!"],
)
def test_malformed_tokens_never_verify_and_never_raise(garbage: str) -> None:
    assert verify_link_token(garbage, secret=_SECRET, now=_NOW) is None


def test_flipping_a_character_in_the_signature_invalidates_the_token() -> None:
    token = generate_link_token(
        "01ARZ3NDEKTSV4RRFFQ69G5FAV", 1, secret=_SECRET, ttl=timedelta(hours=72), now=_NOW
    )
    payload_part, signature = token.rsplit(".", 1)
    flipped_char = "0" if signature[0] != "0" else "1"
    tampered = f"{payload_part}.{flipped_char}{signature[1:]}"
    assert verify_link_token(tampered, secret=_SECRET, now=_NOW) is None


def test_swapping_the_case_id_of_a_valid_token_invalidates_it() -> None:
    token = generate_link_token(
        "01ARZ3NDEKTSV4RRFFQ69G5FAV", 1, secret=_SECRET, ttl=timedelta(hours=72), now=_NOW
    )
    forged = generate_link_token(
        "01ARZ3NDEKTSV4RRFFQ69G5FAW", 1, secret="wrong-guess", ttl=timedelta(hours=72), now=_NOW
    )
    # can't just splice another case_id's payload onto this token's signature
    payload_part, _ = forged.split(".", 1)
    _, real_signature = token.split(".", 1)
    spliced = f"{payload_part}.{real_signature}"
    assert verify_link_token(spliced, secret=_SECRET, now=_NOW) is None
