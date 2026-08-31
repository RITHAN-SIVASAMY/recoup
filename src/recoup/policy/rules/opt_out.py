"""REG-COMM-03: opt-out is honoured immediately, permanently, and across every
case for that customer.

The cross-case propagation itself is the caller's responsibility — whoever
builds a `PolicyContext` must set `opted_out=True` for *every* case belonging to
a customer whose opt-out has ever been recorded, not just the case the opt-out
event arrived on (`regulatory.opt_out.propagate_all_cases`). This function is
deliberately trivial: the guarantee lives in how `opted_out` gets computed, not
in a branch here — but it exists so the rule has a name, a file, and a test
matching docs/06-COMPLIANCE-MATRIX.md's mapping, the same as every other rule.
"""

from __future__ import annotations


def blocks_contact(opted_out: bool) -> bool:
    return opted_out
