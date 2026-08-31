"""Load trained model artifacts from `ml/artifacts/`. Cached — a model doesn't
change between calls within one process."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib

ARTIFACT_ROOT = Path("ml/artifacts")


class ArtifactsUnavailableError(RuntimeError):
    """Raised when `make train` hasn't run yet. Callers must degrade, not crash."""


@lru_cache
def _load(relative_path: str) -> Any:
    path = ARTIFACT_ROOT / relative_path
    if not path.exists():
        raise ArtifactsUnavailableError(
            f"{path} does not exist — run `make train` (or `uv run python ml/train_*.py`) first"
        )
    return joblib.load(path)


def classifier_model() -> Any:
    return _load("classifier/model.joblib")


def classifier_calibrator() -> Any:
    return _load("classifier/calibrator.joblib")


def propensity_model(arm: str) -> Any:
    return _load(f"propensity_{arm}/model.joblib")


def propensity_calibrator(arm: str) -> Any:
    return _load(f"propensity_{arm}/calibrator.joblib")


def uplift_component(name: str) -> Any:
    return _load(f"uplift/{name}.joblib")
