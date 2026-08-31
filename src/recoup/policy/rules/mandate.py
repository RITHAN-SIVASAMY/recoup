"""REG-MAND-01/02/03/04/05: e-mandate / UPI Autopay retry rules.

`mandate_revoked` and `mandate_insufficient_balance` are never silently retried
(REG-MAND-01); `mandate_technical_failure` retries obey a cadence cap and a
minimum gap (REG-MAND-02); a retry above the AFA threshold needs
re-authorization instead of an automated debit attempt (REG-MAND-04/05); and a
retry is withheld until pre-debit notice is confirmed sent where required
(REG-MAND-03).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal


def is_never_retry_cause(root_cause: str | None, never_retry_causes: list[str]) -> bool:
    return root_cause in never_retry_causes


def exceeds_cadence_cap(attempts_this_cycle: int, max_per_cycle: int) -> bool:
    return attempts_this_cycle >= max_per_cycle


def violates_minimum_gap(last_retry_at: datetime | None, now: datetime, min_gap: timedelta) -> bool:
    if last_retry_at is None:
        return False
    return now - last_retry_at < min_gap


def requires_pre_debit_notice(*, required: bool, already_sent: bool) -> bool:
    return required and not already_sent


def requires_additional_authentication(amount_inr: Decimal, afa_threshold_inr: Decimal) -> bool:
    """REG-MAND-05: above this value, a debit attempt needs AFA — a re-auth link,
    never an automated retry (REG-MAND-04)."""
    return amount_inr >= afa_threshold_inr
