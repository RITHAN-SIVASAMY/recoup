"""CI metric gate for the ML models — fails the build if macro-F1 < .85, Brier > .12 or Qini <= 0.

Stub until Phase 03 trains the classifier, propensity and uplift models; there is nothing to
gate yet, so this exits 0 rather than pretending a model exists.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("metric_gate: no trained models yet (lands in Phase 03) — nothing to gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
