"""The synthetic generator: determinism, merchant-profile sanity, and ground-truth leakage.

Ground-truth leakage matters enough to be its own DoD line: the columns that let
Phase 03 validate the uplift model against a known answer must never be reachable
from anything a model — or this system's own ingestion path — could see at
inference time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recoup.data.generate import GroundTruth, _sha256_of, _write_jsonl, generate_batch
from recoup.data.merchants import MERCHANT_PROFILES
from recoup.ingestion.models import NormalizedIntake

pytestmark = pytest.mark.unit


def test_merchant_profile_weights_sum_to_one() -> None:
    for profile in MERCHANT_PROFILES:
        assert sum(profile.source_type_weights.values()) == pytest.approx(1.0)


def test_generate_batch_is_deterministic_for_a_given_seed() -> None:
    first = generate_batch(seed=42, n_cases=50)
    second = generate_batch(seed=42, n_cases=50)

    assert [i.model_dump(mode="json") for i in first.intake] == [
        i.model_dump(mode="json") for i in second.intake
    ]
    assert [g.model_dump(mode="json") for g in first.ground_truth] == [
        g.model_dump(mode="json") for g in second.ground_truth
    ]


def test_different_seeds_produce_different_batches() -> None:
    a = generate_batch(seed=1, n_cases=50)
    b = generate_batch(seed=2, n_cases=50)

    assert [i.provider_event_id for i in a.intake] != [i.provider_event_id for i in b.intake]


def test_make_data_seed_42_twice_is_hash_identical(tmp_path: Path) -> None:
    batch_a = generate_batch(seed=42, n_cases=30)
    batch_b = generate_batch(seed=42, n_cases=30)

    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    _write_jsonl(path_a, list(batch_a.intake))
    _write_jsonl(path_b, list(batch_b.intake))

    assert _sha256_of(path_a) == _sha256_of(path_b)


def test_ground_truth_fields_never_overlap_with_normalized_intake_fields() -> None:
    intake_fields = set(NormalizedIntake.model_fields.keys())
    ground_truth_fields = set(GroundTruth.model_fields.keys())

    overlap = intake_fields & ground_truth_fields

    assert overlap == {"provider_event_id"}  # the join key, and only the join key


def test_ground_truth_values_never_appear_in_the_ingested_payload() -> None:
    # Note: error_reason legitimately equals true_root_cause's string for the
    # un-confused majority of cases (e.g. "insufficient_funds" is both a valid
    # observable decline reason and a valid taxonomy label) — that's a strong
    # feature, not a leak. The leakage contract is about *keys*, not incidental
    # string equality, which is why this checks field names rather than searching
    # the payload's JSON for the label text.
    batch = generate_batch(seed=42, n_cases=50)
    ground_truth_keys = {"p_self_heal", "p_recover_by_channel", "true_root_cause"}

    for intake, truth in zip(batch.intake, batch.ground_truth, strict=True):
        payload = intake.to_case_created_payload()
        assert not (ground_truth_keys & payload.keys())
        payload_json = json.dumps(payload)
        assert str(truth.p_self_heal) not in payload_json


def test_every_payment_or_mandate_failure_case_has_a_true_root_cause() -> None:
    batch = generate_batch(seed=42, n_cases=60)

    for intake, truth in zip(batch.intake, batch.ground_truth, strict=True):
        if intake.source_type in ("payment_failure", "mandate_failure"):
            assert truth.true_root_cause is not None
        else:
            assert truth.true_root_cause is None
