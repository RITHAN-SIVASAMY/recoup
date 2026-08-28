# CLAUDE.md — Recoup

This file is loaded automatically in every Claude Code session in this repository. Read it fully before writing code.

---

## What this is

**Recoup** is an autonomous, risk-aware revenue recovery agent for Razorpay merchants. It detects revenue at risk from four sources (failed payments, checkout abandonment, failed UPI Autopay/e-mandate renewals, overdue B2B receivables), diagnoses the root cause, decides whether chasing is worth it, executes a bounded and compliant recovery workflow, and proves its impact against a held-out control group.

Built for the Razorpay AI Buildathon, Track 03 — AI Revenue Recovery.

**The specification is authoritative.** `docs/` is a git submodule containing the FRD, architecture, execution plan, evaluation protocol and compliance matrix. If your instinct conflicts with those documents, the documents win — or you propose an ADR and ask. Never silently drift from the spec.

---

## The ten ground rules

1. **The LLM never executes.** No LLM call may send a message, attempt a charge, change case state, or make a policy decision. The model classifies-assists, drafts copy, extracts structured data, converses inside a bounded graph, and explains from retrieved records. Nothing else.
2. **No unlogged side effects.** Every state change appends a `CaseEvent` through `EventStore.append`. Writing to the `cases` table directly is a bug, and an architecture test fails on it.
3. **Policy is data, not code paths.** Rules live in `policies/*.yaml`. A scattered `if root_cause == "...":` in a service is a defect. Regulatory rules live in a separate file from merchant-tunable business policy and are not merchant-editable.
4. **Deterministic first.** Seeded randomness everywhere, frozen clocks in tests, no network in unit tests, no branching on wall-clock time outside the policy layer.
5. **Exact money.** `Decimal` (or integer paise) for all money. Never `float`. UTC internally; IST only at display and quiet-hours boundaries.
6. **Every external call is fallible.** Bounded retries with jitter, explicit timeouts, circuit breakers. Never mutate case state optimistically before a call succeeds.
7. **Tests are part of the deliverable.** Property-based invariant tests for policy, replay-equality for the event log, golden sets for every LLM path. Write the invariant test before the implementation for anything in `policy/`.
8. **Type it.** `mypy --strict` passes on `domain/`, `policy/`, `economics/`, `measurement/`, `audit/`. Pydantic v2 models at every boundary.
9. **Honest metrics only.** If a result is not statistically significant, the code prints that it is not significant. Never add a code path that can make a null look like a win.
10. **Small, meaningful commits.** Conventional Commits, one logical change each, with a `Phase:` trailer.

---

## The authority boundary (memorize this table)

| Capability | LLM may | Deterministic code must |
|---|---|---|
| Classify root cause | assist / explain | own the decision (trained model) |
| Score uplift, compute EV | never | own entirely |
| Decide if an action is permitted | never | own entirely (policy engine) |
| Choose channel and send time | never | own (bandit, constrained to permitted arms) |
| Draft message copy | yes, schema-validated + safety-checked | approve, render, dispatch |
| Run a voice call | yes, inside a bounded graph | own the graph, exits and recording |
| Extract a promise-to-pay | yes, into a strict schema | validate, threshold, gate low confidence to a human |
| Answer "why did this happen?" | yes, from retrieved log entries only | enforce citations and refusal |
| Execute a retry, charge or contact | **never** | own entirely |

Model failure may degrade polish. It may never degrade safety.

---

## Repository map

```
CLAUDE.md            you are here
docs/                git submodule → recoup-docs (the specification)
context/             per-phase context files — read the one for your phase
policies/            policy-as-code YAML (regulatory.yaml is separate and privileged)
src/recoup/
  domain/            Case, CaseEvent, value objects, canonical JSON — zero I/O
  ingestion/         webhooks, importers, dedupe, DLQ
  understanding/     classifier, propensity, uplift, LTV, scoring
  economics/         cost model, EV engine, fatigue budget
  policy/            pure evaluator, YAML loader, simulator
  execution/         channel ports, adapters, staging, idempotency, links
  voice/             dialogue graph, TTS/ASR, transcripts
  measurement/       cohorts, adaptive holdout, statistics
  audit/             event store, hash chain, replay, grounded Q&A
  llm/               Claude client, schemas, prompts, redaction, safety
  api/               FastAPI routes + SSE
  workers/           arq tasks
ml/                  training scripts, model cards, metrics artifacts
data/                seeded synthetic generator + fixtures
tests/               unit · property · integration · chaos · llm_eval
web/                 Next.js dashboard + public recovery microsite
```

---

## Working agreement for each session

1. Read `context/shared/*.md` and the context file for the current phase.
2. **Restate the objective, the definition of done, and your plan before writing code.** Wait for approval.
3. Build. Prefer small vertical slices that keep `make demo` working.
4. Run `make gate PHASE=NN`. Do not declare a phase done on a red gate.
5. Commit with the phase trailer. If anything cost more than 15 minutes, add an entry to `docs/09-INCIDENT-LOG.md`.

## Commands

```bash
make setup      # deps, database, migrations, pre-commit
make data       # regenerate the seeded synthetic batch (SEED=42)
make train      # train models, write metrics + model cards
make run        # api + worker + web
make demo       # end-to-end batch; prints the headline block
make replay     # rebuild projections from the event log
make verify     # hash-chain verification + replay equality
make chaos      # run the chaos suite
make gate PHASE=NN   # the acceptance gate for a phase
```

## Anti-patterns that fail review

- An LLM call in a code path that decides or executes anything
- A `float` holding money
- A rule expressed in Python that belongs in YAML
- A test that reaches the network, or depends on `datetime.now()`
- A metric printed without its uncertainty
- A `try/except` that swallows an error without an event and an exception-queue entry
- A "temporary" direct write to `cases`
- New third-party services added without an ADR
