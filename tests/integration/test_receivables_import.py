"""CSV-driven receivables import (FR-1.4), against a real Postgres."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.audit.event_store import EventStore, create_engine
from recoup.domain.ids import new_ulid
from recoup.ingestion.receivables_import import import_receivables, read_csv_rows

pytestmark = pytest.mark.integration


def _write_csv(tmp_path: Path, invoice_id: str) -> Path:
    path = tmp_path / "receivables.csv"
    path.write_text(
        "invoice_id,amount,customer_ref,due_date,merchant_id,terms\n"
        f"{invoice_id},75000.00,acct_test,2026-01-01,demo,net-30\n",
        encoding="utf-8",
    )
    return path


async def test_import_receivables_creates_one_case_per_row(tmp_path: Path) -> None:
    engine: AsyncEngine = create_engine()
    invoice_id = f"INV-{new_ulid()}"
    csv_path = _write_csv(tmp_path, invoice_id)
    rows = read_csv_rows(csv_path)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)
    async with sessionmaker() as session:
        results = await import_receivables(
            session,
            event_store,
            rows,
            default_merchant_id="demo",
            now=datetime(2026, 2, 1, tzinfo=UTC),
        )

    assert len(results) == 1
    assert results[0].created is True

    events = await event_store.events_for(results[0].case_id)
    assert events[0].event_type == "case.created"
    assert events[0].payload["provider_event_id"] == invoice_id
    assert events[0].payload["days_overdue"] == 31

    await engine.dispose()


async def test_reimporting_the_same_invoice_is_deduped() -> None:
    engine = create_engine()
    invoice_id = f"INV-{new_ulid()}"
    row = {
        "invoice_id": invoice_id,
        "amount": "1000.00",
        "customer_ref": "acct_1",
        "due_date": datetime(2026, 1, 1, tzinfo=UTC),
        "merchant_id": "demo",
        "terms": "net-30",
    }

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    event_store = EventStore(engine)
    async with sessionmaker() as session:
        first = await import_receivables(session, event_store, [row], default_merchant_id="demo")
    async with sessionmaker() as session:
        second = await import_receivables(session, event_store, [row], default_merchant_id="demo")

    assert first[0].case_id == second[0].case_id
    assert first[0].created is True
    assert second[0].created is False

    await engine.dispose()
