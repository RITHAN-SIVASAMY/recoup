"""FastAPI application entry point. Routes land phase by phase."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from recoup.api.approvals import router as approvals_router
from recoup.api.recovery import router as recovery_router
from recoup.api.recovery import webhook_router as recovery_webhook_router
from recoup.ingestion.webhook import router as webhook_router
from recoup.settings import get_settings

app = FastAPI(title="Recoup", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # The public recovery microsite (Phase 07) is a separate Next.js origin;
    # only its own configured origin may call the /api/recovery/* browser
    # endpoints, and only with the methods those routes actually use.
    allow_origins=[get_settings().public_base_url],
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)
app.include_router(webhook_router)
app.include_router(approvals_router)
app.include_router(recovery_router)
app.include_router(recovery_webhook_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
