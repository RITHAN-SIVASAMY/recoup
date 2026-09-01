"""FR-13/§7: `make demo`'s orchestration, end to end against real Postgres,
Redis and the trained model artifacts. Small batch sizes keep this fast;
a manual `make demo` is what proves it at the full 500-case scale.

`run_batch`'s byte-identical-across-seeded-runs property (§7: "two runs from
the same seed must produce byte-identical headline numbers") is a claim
about two runs against a *fresh* database -- exactly what `git clone && make
setup && make demo` gives on a clean checkout. It is not re-verified here as
"call run_batch twice in one test": `ingest()`'s own dedupe is keyed on
`(source_type, provider_event_id)`, which a fixed seed reproduces exactly,
so a second call against the *same already-populated* dev database would
hit the dedupe/idempotency-guard paths instead of a fresh run and prove
nothing about reproducibility -- it would prove the opposite thing (that a
second pass over already-processed cases behaves differently, which it
correctly does). The determinism this property actually rests on --
`generate_batch`, `measurement.cohort.assign_cohorts`, and
`data.simulate.simulate_resolved` -- is proven directly, and independently
of any database, in their own unit/property test suites.
"""

from __future__ import annotations

import random

import pytest

from recoup.demo import run_batch

pytestmark = pytest.mark.integration

# The dev database is shared and persistent across runs of this suite (see
# tests/integration/test_generator_ingest.py's own note): a fixed literal
# seed would collide with itself on rerun -- ingest()'s dedupe would return
# the *same* case_ids, and a second pass over already-processed cases hits
# the idempotency guard / terminal-state policy checks instead of exercising
# a fresh run, which proves nothing (or the wrong thing). Draw fresh from OS
# entropy each run instead, same fix as INC-008.
_entropy = random.SystemRandom()
_N_CASES = 40


async def test_run_batch_completes_and_produces_a_structurally_sound_report() -> None:
    report = await run_batch(seed=_entropy.randint(1, 2**31 - 1), n_cases=_N_CASES)

    assert report.inputs.n_cases_total == _N_CASES
    assert report.inputs.n_treated + report.inputs.n_control == _N_CASES
    assert report.inputs.audit_chain_verified is True
    assert report.inputs.replay_equality_passed is True
    assert report.significance.n_treated == report.inputs.n_treated
    assert report.significance.n_control == report.inputs.n_control


async def test_no_case_is_double_counted_between_the_two_arms() -> None:
    report = await run_batch(seed=_entropy.randint(1, 2**31 - 1), n_cases=_N_CASES)
    assert report.inputs.n_treated + report.inputs.n_control == report.inputs.n_cases_total
