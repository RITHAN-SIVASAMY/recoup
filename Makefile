SHELL := /bin/bash
SEED  ?= 42
CASES ?= 2000  # 500 is under-powered for this system's true effect size (MDE ~18pp); 2000 gets MDE to ~9pp
PHASE ?= 00

.PHONY: help setup data train run demo replay verify chaos test lint types gate docx clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

setup:      ## install deps, start datastores, run migrations, install hooks
	uv sync --all-extras
	docker compose up -d postgres redis
	uv run alembic upgrade head
	uv run pre-commit install
	cd web && npm install

data:       ## regenerate the seeded synthetic batch
	uv run python -m recoup.data.generate --seed $(SEED) --cases 500

train:      ## train models, write metrics and model cards
	uv run python ml/train_classifier.py
	uv run python ml/train_propensity.py
	uv run python ml/train_uplift.py

run:        ## api + worker + web
	docker compose up --build

demo:       ## run the batch end to end and print the headline block
	uv run python -m recoup.cli demo --seed $(SEED) --cases $(CASES)

replay:     ## rebuild projections from the event log
	uv run python -m recoup.cli replay

verify:     ## hash-chain verification + replay equality
	uv run python -m recoup.cli verify

chaos:      ## failure-injection suite
	uv run pytest -m chaos -q

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check . && uv run lint-imports

types:
	uv run mypy src/recoup

gate:       ## the acceptance gate for a phase: make gate PHASE=04
	@echo "── gate: phase $(PHASE) ──"
	$(MAKE) lint && $(MAKE) types && uv run pytest -q -m "not llm_eval" \
		&& uv run python scripts/phase_gate.py --phase $(PHASE)

docx:       ## regenerate the .docx exports of the headline documents
	cd docs && pandoc 01-FRD.md -o exports/Recoup_FRD_v2.docx --toc
	cd docs && pandoc 02-PROBLEM-AND-DIFFERENTIATION.md -o exports/Recoup_Problem_Differentiation_v2.docx --toc

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
