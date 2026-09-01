"""FR-4.5: the rolling per-customer contact-fatigue budget (default 3 / 30 days,
across all cases). The cap itself lives in `policies/regulatory.yaml` and is
enforced as a hard DENY at REG-COMM-06 (`policy/evaluator.py`) — this module is
the read-only economics-side view of the same budget, used to steepen the
goodwill curve and to skip pricing a contact candidate that's already spent.
Pure — no I/O.
"""

from __future__ import annotations

from recoup.policy.schema import ContactFatigue


def remaining_contact_budget(contacts_sent: int, fatigue: ContactFatigue) -> int:
    return max(0, fatigue.max_contacts - contacts_sent)


def is_fatigued(contacts_sent: int, fatigue: ContactFatigue) -> bool:
    return contacts_sent >= fatigue.max_contacts
