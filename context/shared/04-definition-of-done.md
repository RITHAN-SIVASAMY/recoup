# Shared context · Definition of done

A phase is done when **all** of these are true. There is no partial credit; a red gate means the phase is not done.

## Universal gate

- [ ] `make gate PHASE=NN` is green
- [ ] `ruff check`, `ruff format --check`, `mypy` (strict scope) all pass
- [ ] New code has tests at the right level (unit / property / integration / chaos / llm_eval)
- [ ] No new `# type: ignore`, `# noqa`, or skipped test without an inline reason
- [ ] `make demo` still runs end-to-end (from Phase 02 onward, this is non-negotiable)
- [ ] `make verify` passes (hash chain + replay equality) from Phase 01 onward
- [ ] Every new state change writes a `CaseEvent`
- [ ] Docs updated if behaviour diverged from the FRD, or an ADR written if a decision was made
- [ ] Committed with a `Phase:` trailer and tagged `phase-NN`
- [ ] `docs/09-INCIDENT-LOG.md` updated if anything cost more than 15 minutes

## Phase-specific gates

| Phase | Gate |
|---|---|
| 00 | Clean clone → `make setup` → green CI |
| 01 | Replay equality; tamper detection names the divergent event; duplicate idempotency key → one effect |
| 02 | 100× webhook replay → 1 case, 0 actions; malformed payload → DLQ + exception; `make data SEED=42` hash-identical |
| 03 | macro-F1 ≥ 0.85, Brier ≤ 0.12, Qini > 0; model cards include Known failure modes; CI metric gate live |
| 04 | All Hypothesis invariants green; ≥3 demonstrated blocks with rule IDs; no execution path without a logged verdict |
| 05 | A case terminates `abandoned_uneconomic` with visible arithmetic; a staged action is cancelled and never sends; kill switch halts everything |
| 06 | Full happy path through the simulator; bandit provably never selects a denied arm |
| 07 | Link opened on a phone → test-mode payment → case flips to `recovered` over SSE; link reuse refused |
| 08 | Recorded call with a captured PTP; escalation suspended until the promised date; out-of-graph input degrades safely |
| 09 | 40-question benchmark green; one cited answer and one refusal demonstrated live |
| 10 | Headline block printed and byte-identical across two seeded runs; non-significant results labelled as such |
| 11 | All 14 FRD acceptance criteria reachable in ≤2 clicks; chaos scenarios visibly safe |
| 12 | Stranger clones, runs `make demo`, gets the same numbers; deployed URL live; video ≤5:00 |
