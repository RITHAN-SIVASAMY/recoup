"""Pydantic schema for `policies/*.yaml` — loader.py validates against this
before anything is hashed into a `policy_version` or handed to `evaluate()`.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from recoup.domain.models import ActionType, Channel
from recoup.policy.duration import parse_duration

TimeOfDay = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class QuietHours(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start: TimeOfDay
    end: TimeOfDay
    tz: str


class Consent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    required_channels: list[Channel]


class OptOut(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    propagate_all_cases: bool


class ContactFatigue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_contacts: int = Field(ge=0)
    window: timedelta

    @field_validator("window", mode="before")
    @classmethod
    def _parse_window(cls, value: object) -> object:
        return parse_duration(value) if isinstance(value, str) else value


class MandateRetry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    never_retry_causes: list[str]
    max_per_cycle: int = Field(ge=0)
    min_gap: timedelta
    pre_debit_notice_required: bool
    afa_threshold_inr: Decimal

    @field_validator("min_gap", mode="before")
    @classmethod
    def _parse_min_gap(cls, value: object) -> object:
        return parse_duration(value) if isinstance(value, str) else value


class RegulatoryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    quiet_hours: QuietHours
    consent: Consent
    opt_out: OptOut
    contact_fatigue: ContactFatigue
    mandate_retry: MandateRetry


class LadderStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ActionType
    channels: list[Channel] | None = None
    wait_before: timedelta

    @field_validator("wait_before", mode="before")
    @classmethod
    def _parse_wait_before(cls, value: object) -> object:
        return parse_duration(value) if isinstance(value, str) else value


class Ladder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str
    steps: list[LadderStep]
    forbidden_actions: list[ActionType] = Field(default_factory=list)


class LaddersPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    ladders: dict[str, Ladder]


class MerchantEconomics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ev_floor_inr: Decimal


class MerchantApproval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value_threshold_inr: Decimal
    always_require: list[ActionType] = Field(default_factory=list)


class MerchantPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    merchant_id: str
    economics: MerchantEconomics
    approval: MerchantApproval
    exposure_cap_inr: Decimal
    kill_switch: bool = False


class PolicyBundle(BaseModel):
    """Everything `evaluate()` needs, plus the content hash that becomes `policy_version`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    regulatory: RegulatoryPolicy
    ladders: LaddersPolicy
    merchant: MerchantPolicy
    policy_version: str
