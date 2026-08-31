"""FastAPI application entry point. Routes land phase by phase."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Recoup", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
