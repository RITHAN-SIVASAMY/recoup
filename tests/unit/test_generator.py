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
    batch = generate_batch(seed=42, n_cases=20)
    ground_truth_keys = {"p_self_heal", "p_recover_by_channel"}

    for intake, truth in zip(batch.intake, batch.ground_truth, strict=True):
        payload = intake.to_case_created_payload()
        assert not (ground_truth_keys & payload.keys())
        payload_json = json.dumps(payload)
        assert str(truth.p_self_heal) not in payload_json
