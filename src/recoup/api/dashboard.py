"""FR-15: the merchant dashboard's read surface, plus FR-16.7's live "Break
it" control. Thin by design -- aggregation lives in `api/dashboard_data.py`,
chaos scenarios live in `chaos/scenarios.py`; this module only wires HTTP to
them.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from recoup.api import dashboard_data
from recoup.api.deps import get_engine, get_event_store, get_policy, get_redis
from recoup.audit.event_store import EventStore
from recoup.audit.projection import project
from recoup.audit.qa import ask
from recoup.chaos import scenarios as chaos_scenarios
from recoup.policy.schema import PolicyBundle

router = APIRouter(prefix="/dashboard")

_ARTIFACT_ROOT = Path("ml/artifacts")
_REPORTS_DIR = Path("data/reports")


def _decimal_safe(value: object) -> object:
    """Dashboard JSON never silently float-converts money -- explicit `str`."""
    if isinstance(value, Decimal):
        return str(value)
    return value


def _row(obj: object, fields: list[str]) -> dict[str, object]:
    return {field: _decimal_safe(getattr(obj, field)) for field in fields}


# ── FR-15.1 batch summary ────────────────────────────────────────────────


@router.get("/summary")
async def batch_summary(
    event_store: Annotated[EventStore, Depends(get_event_store)],
) -> dict[str, object]:
    # Single-tenant demo build: one policy ("demo") governs cases carrying
    # several different business-profile merchant_id labels (demo-d2c,
    # demo-subscription, demo-b2b from the generator) -- so dashboard reads
    # never filter by merchant_id, they read every case there is.
    #
    # Audit-chain/replay status is read from the stored batch report (verified
    # once, when `make demo` produced it) rather than re-verified live here:
    # a full-log scan over this dev database's entire accumulated history
    # takes tens of seconds and answers a different question than "is the
    # batch this panel is showing trustworthy" -- `recoup verify` / `make
    # verify` is the tool for "is the whole log intact right now".
    report = dashboard_data.latest_batch_report()
    states = await dashboard_data.cases_by_state(event_store)
    chain_verified = bool(report.get("audit_chain_verified")) if report else False
    replay_ok = bool(report.get("replay_equality_passed")) if report else False
    return {
        "batch_report": report,  # None if `make demo` hasn't run yet -- shown as-is, never faked
        "cases_by_state": states,
        "audit_chain_verified": chain_verified,
        "replay_equality_passed": replay_ok,
    }


# ── FR-15.2 work queue ───────────────────────────────────────────────────


@router.get("/queue")
async def get_work_queue(
    event_store: Annotated[EventStore, Depends(get_event_store)],
    limit: int = 50,
) -> list[dict[str, object]]:
    items = await dashboard_data.work_queue(event_store, limit=limit)
    return [
        _row(
            item,
            [
                "case_id",
                "root_cause",
                "amount_at_risk",
                "uplift",
                "uplift_segment",
                "expected_value_inr",
                "reason",
                "updated_at",
            ],
        )
        for item in items
    ]


# ── FR-15.3 exception queue (approval queue + kill switch already exist
#    in api/approvals.py) ────────────────────────────────────────────────


@router.get("/exceptions")
async def get_exception_queue(
    event_store: Annotated[EventStore, Depends(get_event_store)],
) -> list[dict[str, object]]:
    items = await dashboard_data.exception_queue(event_store)
    return [
        _row(item, ["case_id", "root_cause", "amount_at_risk", "reason", "occurred_at"])
        for item in items
    ]


# ── FR-15.4 case timeline ────────────────────────────────────────────────


@router.get("/cases/{case_id}/timeline")
async def case_timeline(
    case_id: str, event_store: Annotated[EventStore, Depends(get_event_store)]
) -> dict[str, object]:
    events = await event_store.events_for(case_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    case = project(events)
    return {
        "case": _row(
            case,
            [
                "case_id",
                "merchant_id",
                "source_type",
                "amount_at_risk",
                "resolution_state",
                "cohort",
                "root_cause",
                "created_at",
                "updated_at",
            ],
        ),
        "events": [
            {
                "event_id": e.event_id,
                "seq": e.seq,
                "occurred_at": e.occurred_at.isoformat(),
                "event_type": e.event_type,
                "actor": {"kind": e.actor.kind, "identifier": e.actor.identifier},
                "payload": json.loads(json.dumps(e.payload, default=str)),
                "policy_version": e.policy_version,
                "model_versions": e.model_versions,
            }
            for e in events
        ],
    }


# ── FR-15.6 compliance view ──────────────────────────────────────────────


@router.get("/compliance")
async def compliance_view(
    event_store: Annotated[EventStore, Depends(get_event_store)],
) -> dict[str, object]:
    tally = await dashboard_data.compliance_view(event_store)
    return {
        "blocked_by_category": tally.blocked_by_category,
        "total_blocked": tally.total_blocked,
    }


# ── FR-15.7 model transparency ───────────────────────────────────────────


def _read_metrics(model_dir: str) -> dict[str, Any] | None:
    path = _ARTIFACT_ROOT / model_dir / "metrics.json"
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _known_failure_modes(metrics: dict[str, Any] | None) -> list[str]:
    if metrics is None or "confusion_matrix" not in metrics or "class_labels" not in metrics:
        return []
    labels: list[str] = metrics["class_labels"]
    matrix: list[list[int]] = metrics["confusion_matrix"]
    notes: list[str] = []
    for i, true_label in enumerate(labels):
        row = matrix[i]
        row_total = sum(row)
        if row_total == 0:
            continue
        for j, predicted_label in enumerate(labels):
            if i == j or row[j] == 0:
                continue
            share = row[j] / row_total
            if share >= 0.10:  # a confusion worth naming, not single-digit noise
                notes.append(
                    f"{true_label} is mistaken for {predicted_label} in "
                    f"{share:.0%} of its held-out cases"
                )
    return notes


@router.get("/models")
async def model_transparency() -> dict[str, object]:
    models = {}
    for name, model_dir in (
        ("classifier", "classifier"),
        ("propensity_baseline", "propensity_baseline"),
        ("propensity_treated", "propensity_treated"),
        ("uplift", "uplift"),
    ):
        metrics = _read_metrics(model_dir)
        models[name] = {
            "metrics": metrics,
            "known_failure_modes": _known_failure_modes(metrics) if name == "classifier" else [],
            "available": metrics is not None,
        }
    return {"models": models}


# ── FR-14.5 grounded Q&A, surfaced on the dashboard ──────────────────────


class QARequest(BaseModel):
    case_id: str
    question: str


@router.post("/qa")
async def grounded_qa(
    body: QARequest, engine: Annotated[AsyncEngine, Depends(get_engine)]
) -> dict[str, object]:
    result = await ask(engine, case_id=body.case_id, question=body.question, now=datetime.now(UTC))
    return {
        "answer": result.answer,
        "citations": list(result.citations),
        "refused": result.refused,
        "refusal_reason": result.refusal_reason,
        "degraded_mode": result.degraded_mode,
        "prompt_version": result.prompt_version,
        "prompt_hash": result.prompt_hash,
    }


# ── FR-15.5 what-if simulator ────────────────────────────────────────────


class WhatIfRequest(BaseModel):
    ev_floor_inr: str | None = None
    channel_cost_inr: str | None = None
    approval_threshold_inr: str | None = None
    max_contacts: int | None = None


@router.post("/what-if")
async def what_if(
    body: WhatIfRequest,
    event_store: Annotated[EventStore, Depends(get_event_store)],
    policy: Annotated[PolicyBundle, Depends(get_policy)],
) -> dict[str, object]:
    params = dashboard_data.WhatIfParams(
        ev_floor_inr=Decimal(body.ev_floor_inr) if body.ev_floor_inr is not None else None,
        channel_cost_inr=(
            Decimal(body.channel_cost_inr) if body.channel_cost_inr is not None else None
        ),
        approval_threshold_inr=(
            Decimal(body.approval_threshold_inr)
            if body.approval_threshold_inr is not None
            else None
        ),
        max_contacts=body.max_contacts,
    )
    projection = await dashboard_data.run_what_if(event_store, bundle=policy, params=params)
    return {
        **_row(
            projection,
            [
                "cases_considered",
                "baseline_would_contact",
                "projected_would_contact",
                "newly_contactable",
                "newly_uneconomic",
                "newly_requires_approval",
                "no_longer_requires_approval",
                "newly_over_contact_cap",
            ],
        ),
        "is_projection": True,  # this phase's own guardrail: never presented as a measurement
    }


# ── FR-15.8 audit-ready export ───────────────────────────────────────────


def _latest_report_json_path() -> Path | None:
    if not _REPORTS_DIR.exists():
        return None
    json_files = sorted(_REPORTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return json_files[0] if json_files else None


@router.get("/export")
async def export_latest_batch(format: str = "json") -> Response:
    if format not in ("json", "markdown"):
        raise HTTPException(status_code=400, detail="format must be 'json' or 'markdown'")
    json_path = _latest_report_json_path()
    if json_path is None:
        raise HTTPException(status_code=404, detail="no batch report exists yet -- run make demo")
    if format == "json":
        return Response(
            content=json_path.read_text(encoding="utf-8"), media_type="application/json"
        )
    md_path = json_path.with_suffix(".md")
    if not md_path.exists():
        raise HTTPException(status_code=404, detail=f"{md_path.name} was not written by that run")
    return Response(content=md_path.read_text(encoding="utf-8"), media_type="text/markdown")


# ── FR-16.7 the live "Break it" control ──────────────────────────────────


@router.get("/chaos/scenarios")
async def list_chaos_scenarios() -> dict[str, str]:
    return chaos_scenarios.SCENARIOS


_NO_REDIS_SCENARIOS = {
    "duplicate_webhook",
    "llm_timeout",
    "llm_invalid_schema",
    "poisoned_model_output",
}


@router.post("/chaos/{scenario}")
async def run_chaos_scenario(
    scenario: str,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, object]:
    runner = {
        "duplicate_webhook": lambda: chaos_scenarios.run_duplicate_webhook(engine),
        "out_of_order_events": lambda: chaos_scenarios.run_out_of_order_events(engine, redis),
        "provider_5xx": lambda: chaos_scenarios.run_provider_5xx(engine, redis),
        "provider_timeout": lambda: chaos_scenarios.run_provider_timeout(engine, redis),
        "worker_crash_mid_action": lambda: chaos_scenarios.run_worker_crash_mid_action(
            engine, redis
        ),
        "llm_timeout": lambda: chaos_scenarios.run_llm_timeout(engine),
        "llm_invalid_schema": lambda: chaos_scenarios.run_llm_invalid_schema(engine),
        "poisoned_model_output": lambda: chaos_scenarios.run_poisoned_model_output(engine),
    }.get(scenario)
    if runner is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown or unsupported-live scenario {scenario!r} "
            "(malformed_payload and clock_skew are proven by the test suite's own "
            "HTTP-boundary tests, not live-runnable here)",
        )
    result = await runner()
    return {
        "scenario": result.scenario,
        "case_id": result.case_id,
        "passed": result.passed,
        "narrative": result.narrative,
        "outcomes": [
            {"label": o.label, "passed": o.passed, "detail": o.detail} for o in result.outcomes
        ],
    }


# ── FR-15.9 live event stream ────────────────────────────────────────────


async def _sse_case_events(engine: AsyncEngine, merchant_id: str) -> Any:
    """Polling-based SSE: no message bus exists yet, so this checks for newly
    updated cases every second and pushes them -- simple, and still genuinely
    live from the browser's point of view (FR-15.9's actual requirement)."""
    event_store = EventStore(engine)
    seen_tip_hashes: dict[str, str] = {}
    try:
        while True:
            cases = await event_store.all_cases(merchant_id=merchant_id)
            for case in cases[:100]:
                if seen_tip_hashes.get(case.case_id) == case.tip_hash:
                    continue
                seen_tip_hashes[case.case_id] = case.tip_hash
                payload = {
                    "case_id": case.case_id,
                    "resolution_state": case.resolution_state,
                    "cohort": case.cohort,
                    "root_cause": case.root_cause,
                    "amount_at_risk": str(case.amount_at_risk),
                    "updated_at": case.updated_at.isoformat(),
                }
                yield f"event: case_update\ndata: {json.dumps(payload)}\n\n"
            yield ": keep-alive\n\n"
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        return


@router.get("/stream")
async def event_stream(
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    policy: Annotated[PolicyBundle, Depends(get_policy)],
) -> StreamingResponse:
    return StreamingResponse(
        _sse_case_events(engine, policy.merchant.merchant_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
