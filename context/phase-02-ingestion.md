# Phase 02 · Ingestion and synthetic data

**Day 2 · full day · Ends with the first demo-able vertical slice.**

## Mission
Four sources in, one `Case` out, nothing ever lost — plus a seeded, realistic 500-case synthetic batch with ground-truth response curves.

## Why judges care
The brief names four sources explicitly. Most submissions handle `payment.failed` only. The DLQ and the duplicate-suppression behaviour are also where "graceful failure handling" first becomes visible.

## Read first
`docs/01-FRD.md` FR-1 · `shared/01-data-contracts.md` · `docs/05-EVALUATION-PROTOCOL.md` §8 (threats to validity — the generator is one)

## Build
- [ ] `ingestion/webhook.py` — FastAPI route, **Razorpay signature verification**, raw payload archived before parsing, unsigned payloads rejected and logged without creating a case
- [ ] `ingestion/dedupe.py` — `(source, provider_event_id)` uniqueness; a duplicate writes `event.duplicate_suppressed` and returns 200
- [ ] Normalizers: `payment_failed.py`, `checkout_abandoned.py`, `mandate_failed.py`, `receivable_overdue.py` → one `Case`
- [ ] `ingestion/mandate_poller.py` — arq cron polling subscription/mandate status changes
- [ ] `ingestion/receivables_import.py` — CSV + API import with due dates, terms, account metadata
- [ ] `ingestion/dlq.py` — unparseable/unverifiable events stored with the raw payload and surfaced as exceptions
- [ ] Late/out-of-order handling: apply by `occurred_at`; a late success event retires in-flight recovery
- [ ] `data/generator.py` — seeded synthetic generator:
  - realistic Indian failure mix and issuer variety, amount distributions, time-of-day and salary-cycle effects
  - **ground-truth per case**: `p_self_heal` and `p_recover | intervention` per channel — used *only* to validate uplift later
  - merchant profiles (D2C, subscription, B2B) with different mixes
  - `make data SEED=42` → hash-identical batch
- [ ] `tests/chaos/test_ingestion_chaos.py` — 100× replay, malformed payload, out-of-order success, clock skew

## Definition of done
- Replaying one webhook 100× → 1 case, 0 actions, 99 suppression events
- Malformed payload → DLQ entry + exception-queue row, HTTP 200 (never a retry storm)
- `make data SEED=42` twice → identical content hash
- Feature-leakage test: ground-truth columns are absent from every feature matrix

## Demo hook
Four source types streaming into the dashboard live, with the DLQ visibly non-empty and handled.

## Guardrails
Ground truth is never readable at inference. The webhook route does no business logic — verify, dedupe, archive, enqueue.

## Cut line
The abandonment tracker may be file-driven rather than a live beacon.

## Prompt seed
> Read `context/phase-02-ingestion.md`. Implement ingestion for all four sources plus the seeded synthetic generator. The generator must emit a ground-truth response curve per case for later uplift validation, and a test must assert those columns can never reach a model at inference time.

## Commit
`feat(ingestion): four-source ingestion with dedupe, DLQ and seeded generator` · `Phase: 02-ingestion` · tag `phase-02`
