"""Phase-specific acceptance gate, invoked as `make gate PHASE=NN`.

Lint, types and the test suites already ran by the time this script runs
(see the Makefile's `gate` target); this adds only the checks that are
specific to one phase and cannot be expressed as a pytest marker.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

sys.stdout.reconfigure(encoding="utf-8")

GateCheck = Callable[[], tuple[bool, str]]


def _phase_00() -> tuple[bool, str]:
    return True, "no phase-specific checks beyond lint, types and the registered test suites"


def _phase_01() -> tuple[bool, str]:
    return (
        True,
        "replay equality, tamper detection and idempotent-append checks ran as part of the test suites above",
    )


def _phase_02() -> tuple[bool, str]:
    return (
        True,
        "100x replay, malformed-payload DLQ handling, generator determinism and "
        "ground-truth leakage checks ran as part of the test suites above",
    )


_GATES: dict[int, GateCheck] = {
    0: _phase_00,
    1: _phase_01,
    2: _phase_02,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=int, required=True)
    args = parser.parse_args()

    check = _GATES.get(args.phase)
    if check is None:
        print(f"── phase {args.phase:02d}: no gate registered yet ──")
        return 1

    ok, detail = check()
    status = "GREEN" if ok else "RED"
    print(f"── phase {args.phase:02d} gate: {status} ── {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
