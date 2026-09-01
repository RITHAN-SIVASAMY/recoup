"""FastAPI application entry point. Routes land phase by phase."""

from __future__ import annotations

from fastapi import FastAPI

from recoup.api.approvals import router as approvals_router
from recoup.ingestion.webhook import router as webhook_router

app = FastAPI(title="Recoup", version="0.1.0")
app.include_router(webhook_router)
app.include_router(approvals_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
