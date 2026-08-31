"""Socket-blocking guard: unit and property tests may never touch the network.

Sockets stay enabled through fixture setup/teardown and are only disabled around the
test body itself: on Windows, pytest-asyncio's event loop needs a real socket for its
internal self-pipe (`ProactorEventLoop`/`socket.socketpair`) during setup, so disabling
too early breaks every async unit test before it gets anywhere near real network I/O.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from pytest_socket import disable_socket, enable_socket


def pytest_runtest_setup(item: pytest.Item) -> None:
    enable_socket()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    markers = {marker.name for marker in item.iter_markers()}
    if "unit" in markers or "property" in markers:
        disable_socket()
    try:
        yield
    finally:
        enable_socket()
