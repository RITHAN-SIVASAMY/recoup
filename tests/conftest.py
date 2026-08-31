"""Socket-blocking guard: unit and property tests may never touch the network."""

from __future__ import annotations

import pytest
from pytest_socket import disable_socket, enable_socket


def pytest_runtest_setup(item: pytest.Item) -> None:
    markers = {marker.name for marker in item.iter_markers()}
    if "unit" in markers or "property" in markers:
        disable_socket()
    else:
        enable_socket()
