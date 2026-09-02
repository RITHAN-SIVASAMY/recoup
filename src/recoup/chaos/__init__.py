"""FR-16: reproducible failure-injection scenarios.

`scenarios.py` holds the actual implementations, each a self-contained,
narratable async function returning a `ScenarioResult`. They are written
once and used twice: `tests/chaos/test_scenarios.py` asserts on them, and
Phase 11's dashboard "Break it" control (FR-16.7) calls the exact same
functions live, so the demo can never drift from what the test suite
actually proves.
"""

from __future__ import annotations
