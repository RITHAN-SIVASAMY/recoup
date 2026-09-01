"""Phase-specific acceptance gate, invoked as `make gate PHASE=NN`.

Lint, types and the test suites already ran by the time this script runs
(see the Makefile's `gate` target); this adds only the checks that are
specific to one phase and cannot be expressed as a pytest marker.
"""

from __future__ import annotations

import argparse
import subprocess
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


def _run(*args: str) -> bool:
    result = subprocess.run(["uv", "run", "python", *args], check=False)
    return result.returncode == 0


def _phase_03() -> tuple[bool, str]:
    # Genuinely phase-specific and not pytest-expressible: retrain on the seeded
    # data and enforce the metric gate (macro-F1, Brier, AUC, Qini). Scoring
    # correctness (model_versions recorded on every event, etc.) is covered by
    # tests/integration/test_scoring.py in the test suites that already ran above
    # — skipped rather than run if this is the very first `make gate PHASE=03` on
    # a fresh clone, since the artifacts this script is about to produce don't
    # exist yet at that point. Re-running the gate a second time exercises both.
    trained = (
        _run("ml/train_classifier.py")
        and _run("ml/train_propensity.py")
        and _run("ml/train_uplift.py")
    )
    if not trained:
        return False, "model training failed — see the output above"
    gated = _run("scripts/metric_gate.py")
    return gated, "retrained on seeded data; see scripts/metric_gate.py's output above"


def _phase_04() -> tuple[bool, str]:
    return (
        True,
        "policy-as-code invariants, quiet-hours/DST edge cases, loader validation and "
        "the policy.evaluated/policy.denied audit trail ran as part of the test suites "
        "above; 'policy imports only domain' is enforced by lint-imports in `make lint`",
    )


def _phase_05() -> tuple[bool, str]:
    return (
        True,
        "EV floor -> case.abandoned_uneconomic with the full ledger, the staged-action "
        "cancel/promote state machine (property-tested), the approval queue's grant/reject "
        "flow and the kill switch's cancel-in-flight-actions behaviour all ran as part of "
        "the test suites above, including over real HTTP against the approvals/killswitch "
        "routes (tests/integration/test_approvals_api.py)",
    )


_GATES: dict[int, GateCheck] = {
    0: _phase_00,
    1: _phase_01,
    2: _phase_02,
    3: _phase_03,
    4: _phase_04,
    5: _phase_05,
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
