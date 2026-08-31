"""Unit tests for policy/loader.py: validation, content hashing, hot reload."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from recoup.policy.loader import PolicyLoader

pytestmark = pytest.mark.unit

REAL_POLICY_DIR = Path("policies")


def _copy_policies(tmp_path: Path) -> Path:
    dest = tmp_path / "policies"
    shutil.copytree(REAL_POLICY_DIR, dest)
    return dest


def test_load_produces_a_valid_bundle_from_the_real_policy_files() -> None:
    bundle = PolicyLoader(REAL_POLICY_DIR).load()
    assert bundle.policy_version
    assert "mandate_revoked" in bundle.ladders.ladders
    assert bundle.merchant.merchant_id == "demo"


def test_loading_twice_without_a_file_change_returns_the_identical_cached_bundle(
    tmp_path: Path,
) -> None:
    policy_dir = _copy_policies(tmp_path)
    loader = PolicyLoader(policy_dir)
    first = loader.load()
    second = loader.load()
    assert first is second  # cached, not re-parsed


def test_editing_a_policy_file_changes_the_content_hash_after_reload(tmp_path: Path) -> None:
    policy_dir = _copy_policies(tmp_path)
    loader = PolicyLoader(policy_dir)
    original_version = loader.load().policy_version

    regulatory_path = policy_dir / "regulatory.yaml"
    data = yaml.safe_load(regulatory_path.read_text(encoding="utf-8"))
    data["contact_fatigue"]["max_contacts"] = 99
    regulatory_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    # mtime resolution can be coarser than the test's own wall-clock speed.
    new_mtime = regulatory_path.stat().st_mtime + 1
    os.utime(regulatory_path, (new_mtime, new_mtime))

    reloaded = loader.load()
    assert reloaded.policy_version != original_version
    assert reloaded.regulatory.contact_fatigue.max_contacts == 99


def test_an_invalid_policy_file_raises_rather_than_silently_loading(tmp_path: Path) -> None:
    policy_dir = _copy_policies(tmp_path)
    ladders_path = policy_dir / "ladders.yaml"
    data = yaml.safe_load(ladders_path.read_text(encoding="utf-8"))
    del data["ladders"]["mandate_revoked"]["steps"]  # required field, now missing
    ladders_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ValidationError):
        PolicyLoader(policy_dir).load()


def test_two_different_merchants_can_load_independent_bundles(tmp_path: Path) -> None:
    policy_dir = _copy_policies(tmp_path)
    other_merchant = policy_dir / "merchant" / "other.yaml"
    other_merchant.write_text(
        (policy_dir / "merchant" / "demo.yaml")
        .read_text(encoding="utf-8")
        .replace("merchant_id: demo", "merchant_id: other")
        .replace('exposure_cap_inr: "500000"', 'exposure_cap_inr: "10000"'),
        encoding="utf-8",
    )

    demo_bundle = PolicyLoader(policy_dir, merchant_id="demo").load()
    other_bundle = PolicyLoader(policy_dir, merchant_id="other").load()

    assert demo_bundle.merchant.exposure_cap_inr != other_bundle.merchant.exposure_cap_inr
