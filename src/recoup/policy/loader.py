"""Parse, validate and content-hash `policies/*.yaml` into a `PolicyBundle`.

Hot-reloads in dev: `PolicyLoader.load()` re-reads and re-validates whenever any
source file's mtime has changed since the last successful load, and otherwise
returns the cached bundle. A load failure never silently keeps a stale bundle
quiet — it raises, because a policy that fails to parse is not a policy that
should keep governing live decisions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from recoup.policy.schema import LaddersPolicy, MerchantPolicy, PolicyBundle, RegulatoryPolicy

DEFAULT_POLICY_DIR = Path("policies")


def _read_yaml(path: Path) -> dict[str, Any]:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} did not parse to a YAML mapping")
    return raw


def _content_hash(*documents: dict[str, Any]) -> str:
    canonical = json.dumps(documents, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


class PolicyLoader:
    def __init__(self, policy_dir: Path = DEFAULT_POLICY_DIR, *, merchant_id: str = "demo") -> None:
        self._regulatory_path = policy_dir / "regulatory.yaml"
        self._ladders_path = policy_dir / "ladders.yaml"
        self._merchant_path = policy_dir / "merchant" / f"{merchant_id}.yaml"
        self._cached: PolicyBundle | None = None
        self._cached_mtimes: tuple[float, float, float] | None = None

    def _mtimes(self) -> tuple[float, float, float]:
        return (
            self._regulatory_path.stat().st_mtime,
            self._ladders_path.stat().st_mtime,
            self._merchant_path.stat().st_mtime,
        )

    def load(self) -> PolicyBundle:
        mtimes = self._mtimes()
        if self._cached is not None and mtimes == self._cached_mtimes:
            return self._cached

        regulatory_raw = _read_yaml(self._regulatory_path)
        ladders_raw = _read_yaml(self._ladders_path)
        merchant_raw = _read_yaml(self._merchant_path)

        bundle = PolicyBundle(
            regulatory=RegulatoryPolicy.model_validate(regulatory_raw),
            ladders=LaddersPolicy.model_validate(ladders_raw),
            merchant=MerchantPolicy.model_validate(merchant_raw),
            policy_version=_content_hash(regulatory_raw, ladders_raw, merchant_raw),
        )
        self._cached = bundle
        self._cached_mtimes = mtimes
        return bundle
