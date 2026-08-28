# Shared context · Coding standards

## Python

- 3.12, `uv`, `pyproject.toml`. Ruff (lint + format), mypy strict on `domain/ policy/ economics/ measurement/ audit/`.
- Pydantic v2 at boundaries; plain dataclasses inside hot loops.
- Async in `api/`, `workers/`, `execution/`. Pure sync in `policy/`, `economics/`, `domain/` — those must be callable from a test with no event loop.
- Dependency direction: `domain` ← everything. `domain` imports nothing from the project. `policy` imports only `domain`. No cycles; an import-linter contract enforces it.
- Errors: one `RecoupError` base; never swallow. Every caught exception either re-raises or writes a `case.exception` event.
- Logging: `structlog`, JSON, with `case_id`, `event_id`, `policy_version` bound in context. Never log PII.
- Config: `pydantic-settings`, one `Settings` object, no `os.getenv` scattered in modules.

## Tests

```
tests/
  unit/          fast, pure, no I/O, frozen clock
  property/      Hypothesis — the policy invariants live here
  integration/   compose-backed Postgres/Redis
  chaos/         failure-injection scenarios
  llm_eval/      golden sets — grounded QA, PTP extraction, message safety
```

- No network in `unit/` or `property/` (enforced by a socket-blocking fixture).
- Deterministic: `freezegun` for time, seeded RNG, fixed fixtures.
- Name tests as sentences: `test_denies_contact_after_opt_out`.
- Coverage ≥80% on `policy/ economics/ measurement/ audit/`; elsewhere, coverage is not a goal.

## TypeScript / Next.js

- Strict mode, no `any`. Server Components by default; client components only where interactivity requires.
- API types generated from the FastAPI OpenAPI schema — never hand-written and never drifting.
- TanStack Query for fetching, `EventSource` for the live stream.
- Tailwind + shadcn/ui. No bespoke design system.
- Every number rendered with its uncertainty where one exists.

## Commits

```
feat(policy): enforce quiet hours at evaluation time

Adds REG-COMM-01 to the regulatory policy file and the short-circuit
check ahead of ladder evaluation. Covers DST and timezone edges.

Phase: 04-policy-engine
Gate: green
```
