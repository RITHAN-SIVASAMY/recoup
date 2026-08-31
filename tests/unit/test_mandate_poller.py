"""Unit tests for the mandate-status poller's control flow (fake source, no DB)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

import recoup.ingestion.mandate_poller as poller_module
from recoup.ingestion.mandate_poller import NullMandateStatusSource, poll_mandate_status

pytestmark = pytest.mark.unit


async def test_null_source_polls_nothing() -> None:
    assert await NullMandateStatusSource().poll_changed_subscriptions() == []


async def test_poll_mandate_status_ingests_each_change_from_the_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed = [
        {
            "payload": {
                "subscription": {
                    "entity": {
                        "id": "sub_1",
                        "status": "halted",
                        "customer_id": "cust_1",
                        "amount": 50000,
                        "created_at": 1750000000,
                        "notes": {},
                    }
                }
            }
        }
    ]

    class FakeSource:
        async def poll_changed_subscriptions(self) -> list[dict[str, Any]]:
            return changed

    @dataclass
    class FakeResult:
        case_id: str
        created: bool

    fake_ingest = AsyncMock(return_value=FakeResult(case_id="fake-case", created=True))
    monkeypatch.setattr(poller_module, "ingest", fake_ingest)

    results = await poll_mandate_status(
        AsyncMock(), AsyncMock(), FakeSource(), default_merchant_id="demo"
    )

    assert len(results) == 1
    assert results[0].case_id == "fake-case"
    assert fake_ingest.await_count == 1
    intake_arg = fake_ingest.await_args.args[2]
    assert intake_arg.provider_event_id == "sub_1:halted"
