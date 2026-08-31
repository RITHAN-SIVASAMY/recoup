"""`PolicyContext` — everything `evaluate()` needs beyond the proposed action itself.

Deliberately not part of `Case`: these are facts about a case's *history and the
moment of evaluation* (now, contact counts, opt-out status, kill switch), not
part of the case's own persisted projection. The caller builds this from the
event log; `evaluate()` never queries anything itself — see the module docstring
on `policy/evaluator.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from recoup.domain.models import Cohort, ResolutionState
from recoup.policy.schema import PolicyBundle


@dataclass(frozen=True)
class PolicyContext:
    now: datetime
    policy: PolicyBundle
    cohort: Cohort | None
    root_cause: str | None
    resolution_state: ResolutionState
    ladder_step_reached: int = 0

    opted_out: bool = False
    consent_channels: frozenset[str] = field(default_factory=frozenset)

    contacts_sent: int = 0
    """Contacts within the contact-fatigue rolling window, across all cases."""

    last_contact_at: dict[str, datetime] = field(default_factory=dict)
    """Per-channel timestamp of the most recent contact, for cooldown checks."""

    retry_charge_attempts: int = 0
    """Attempts of `retry_charge` this debit cycle, for the mandate cadence cap."""

    last_retry_charge_at: datetime | None = None
    pre_debit_notice_sent: bool = False

    is_flagged_account: bool = False
    exposure_used_inr: Decimal = Decimal(0)
    kill_switch_engaged: bool = False
    already_executed_idempotency_keys: frozenset[str] = field(default_factory=frozenset)

    @property
    def contact_fatigue_window(self) -> timedelta:
        return self.policy.regulatory.contact_fatigue.window
