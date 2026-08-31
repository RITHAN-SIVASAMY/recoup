"""Unit tests for Settings loading."""

from __future__ import annotations

import pytest

from recoup.settings import Settings

pytestmark = pytest.mark.unit


def test_settings_load_defaults_without_an_env_file() -> None:
    settings = Settings(_env_file=None)
    assert settings.recoup_env == "local"
    assert settings.recoup_seed == 42
    assert settings.channel_mode == "simulator"
    assert settings.kill_switch is False


def test_settings_reads_seed_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECOUP_SEED", "7")
    settings = Settings(_env_file=None)
    assert settings.recoup_seed == 7
