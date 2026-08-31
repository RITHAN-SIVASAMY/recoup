"""Case, CaseEvent, value objects. Zero I/O — this module imports nothing from the project."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from recoup.domain.ids import Ulid

SourceType = Literal[
    "payment_failure", "checkout_abandonment", "mandate_failure", "receivable_overdue"
]
ResolutionState = Literal[
    "recovered",
    "pending",
    "awaiting_promise",
    "stopped_by_policy",
    "abandoned_uneconomic",
    "exception",
    "control_untouched",
]
Cohort = Literal["treatment", "control"]


class Actor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["system", "model", "human", "provider"]
    identifier: str

    def __str__(self) -> str:
        return f"{self.kind}:{self.identifier}"


class PromiseToPay(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    amount_inr: Decimal
    date: datetime
    condition: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class CaseEvent(BaseModel):
    """An immutable fact about a case. The source of truth."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: Ulid
    case_id: Ulid
    seq: int = Field(ge=1)
    occurred_at: datetime
    recorded_at: datetime
    actor: Actor
    event_type: str
    payload: dict[str, Any]
    policy_version: str | None = None
    model_versions: dict[str, str] | None = None
    prev_hash: str
    hash: str


class Case(BaseModel):
    """One revenue-at-risk event, normalized. A read-only projection of its CaseEvents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: Ulid
    merchant_id: str
    source_type: SourceType
    provider_event_id: str
    amount_at_risk: Decimal
    currency: str = "INR"
    customer_ref: str
    resolution_state: ResolutionState = "pending"
    cohort: Cohort | None = None
    root_cause: str | None = None
    created_at: datetime
    updated_at: datetime
    seq: int = Field(ge=1)
    tip_hash: str
