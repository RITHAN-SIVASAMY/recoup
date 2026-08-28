# Phase 00 · Foundation

**Day 1 · ~3 hours · No business logic in this phase.**

## Mission
Create a repository that is boring, correct, and impossible to make messy later. Everything downstream inherits the discipline set here.

## Why judges care
A clean clone that builds and tests on the first try is the cheapest credibility in the entire submission. It is also the precondition for the reproducibility claim (`make demo` → same numbers) that the evaluation protocol rests on.

## Read first
`../CLAUDE.md` · `shared/*.md` · `docs/03-ARCHITECTURE.md` §13 (repo layout) · `docs/04-EXECUTION-PLAN.md` §3 (stack) and §5 (git strategy)

## Build
- [ ] `pyproject.toml` with uv; dependency groups: `core`, `ml`, `dev`
- [ ] Package skeleton `src/recoup/{domain,ingestion,understanding,economics,policy,execution,voice,measurement,audit,llm,api,workers}` with `__init__.py` and a one-line module docstring each
- [ ] `docker-compose.yml`: Postgres 16, Redis 7, api, worker, web (web may be a stub for now)
- [ ] `Makefile`: `setup data train run demo replay verify chaos gate test lint types docx`
  - `make gate PHASE=NN` runs lint + types + the tests tagged for that phase and prints a green/red summary
  - `make demo` must exist from day one as a **loud placeholder** that exits non-zero with "not implemented yet"
- [ ] Ruff, mypy (strict on the core packages via per-module overrides), pytest with markers `unit|property|integration|chaos|llm_eval`
- [ ] `.pre-commit-config.yaml`: ruff, ruff-format, mypy, gitleaks, conventional-commit check
- [ ] `.github/workflows/ci.yml`: lint → types → unit → property → integration (services: postgres, redis) → upload coverage. ML and LLM-eval jobs added as stubs that skip until their phases land
- [ ] `.env.example` covering every setting the `Settings` object will read
- [ ] `src/recoup/settings.py` with a single `pydantic-settings` `Settings`
- [ ] `README.md` skeleton with the quickstart and a placeholder for the headline block
- [ ] `LICENSE` (MIT), `.gitignore`, `.gitattributes`
- [ ] `docs/` wired as a submodule (see §5 of the execution plan); README states `git clone --recurse-submodules` in the first three lines
- [ ] `import-linter` contract: `domain` imports nothing from the project; `policy` imports only `domain`

## Definition of done
Fresh clone → `make setup` → `make gate PHASE=00` green → first push → CI green. `make demo` fails loudly and honestly.

## Guardrails
No business logic. No database models beyond an empty Alembic baseline. Resist scaffolding "helpful" utilities you have not needed yet.

## Cut line
None. This phase is mandatory and must not exceed half a day.

## Prompt seed
> Read `CLAUDE.md`, `context/shared/*.md` and `context/phase-00-foundation.md`. Scaffold the repository exactly as specified in §13 of `docs/03-ARCHITECTURE.md`. Write no business logic. Show me the file tree and the Makefile targets as a plan before creating anything.

## Commit
`chore(repo): scaffold project, tooling and CI` · `Phase: 00-foundation` · tag `phase-00`
