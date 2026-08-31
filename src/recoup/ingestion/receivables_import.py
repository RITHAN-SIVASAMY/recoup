"""CSV/API import of overdue B2B receivables (FR-1.4)."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from recoup.audit.event_store import EventStore
from recoup.ingestion.ingest import IngestResult, ingest
from recoup.ingestion.normalizers.receivable_overdue import normalize

_REQUIRED_COLUMNS = {"invoice_id", "amount", "customer_ref", "due_date"}


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = _REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"receivables CSV is missing required columns: {sorted(missing)}")
        rows = []
        for row in reader:
            parsed = dict(row)
            parsed["due_date"] = datetime.fromisoformat(row["due_date"]).replace(tzinfo=UTC)
            rows.append(parsed)
    return rows


async def import_receivables(
    session: AsyncSession,
    event_store: EventStore,
    rows: Iterable[dict[str, Any]],
    *,
    default_merchant_id: str,
    now: datetime | None = None,
) -> list[IngestResult]:
    now = now or datetime.now(UTC)
    results = []
    for row in rows:
        intake = normalize(row, default_merchant_id=default_merchant_id, now=now)
        results.append(await ingest(session, event_store, intake))
    return results
