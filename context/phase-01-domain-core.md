# Phase 01 · Domain core and event store

**Day 1 · ~4 hours · The spine of the entire system.**

## Mission
Implement `Case`, `CaseEvent`, the append-only hash-chained event store, projection rebuild, deterministic replay, and idempotency. Every later phase writes through this.

## Why judges care
"Audit trail" is in the track bar. Almost everyone will ship a logs table. Event sourcing with a verifiable hash chain and byte-exact replay is a different category of answer — and it is what makes time travel, the what-if simulator and post-hoc compliance replay possible at all.

## Read first
`shared/01-data-contracts.md` · `docs/03-ARCHITECTURE.md` §5 · `docs/adr/0002-event-sourcing.md`

## Build
- [ ] `domain/canonical.py` — canonical JSON (sorted keys, no whitespace, `Decimal` as string). **One implementation**, used by the hash chain and the dedupe key
- [ ] `domain/models.py` — `Case`, `CaseEvent`, `Actor`, `SourceType`, `ResolutionState`, `PromiseToPay`, frozen Pydantic v2 with `extra="forbid"`
- [ ] Alembic migration: `case_events` (append-only; a DB trigger or revoked UPDATE/DELETE grants), `cases` (projection), unique index on `(case_id, seq)`, unique index on `idempotency_key`
- [ ] `audit/event_store.py` — `append(case_id, event_type, payload, actor, ...)`; computes `prev_hash`/`hash` inside a transaction with `SELECT ... FOR UPDATE` on the case tip. **The only write path for case state**
- [ ] `audit/projection.py` — `project(events) -> Case`; `rebuild_all()` behind `make replay`
- [ ] `audit/verify.py` — walk the chain, return the first divergent event ID; behind `make verify`
- [ ] `execution/idempotency.py` — `idempotency_key(case_id, action_type, ladder_step, policy_version)` plus a Redis SETNX guard and the DB unique index as backstop
- [ ] `tests/conftest.py` — frozen clock, seeded RNG, socket-blocking fixture for unit/property tests
- [ ] Architecture test: no module outside `audit/` may write to `cases`

## Key interface
```python
class EventStore:
    async def append(self, *, case_id: ULID, event_type: str, payload: dict,
                     actor: Actor, occurred_at: datetime | None = None,
                     policy_version: str | None = None,
                     model_versions: dict[str, str] | None = None) -> CaseEvent: ...
    async def events_for(self, case_id: ULID, until: datetime | None = None) -> list[CaseEvent]: ...
```
`events_for(..., until=T)` is time travel; the dashboard timeline is exactly this call.

## Definition of done
- Replay equality: projecting the log reproduces the stored projection byte-for-byte (CI test)
- Tamper test: mutating one payload is detected and the divergent event named
- Property test: two appends with the same idempotency key produce exactly one effect
- Concurrency test: two workers appending to one case produce a gapless `seq` with no lost update

## Demo hook
`make verify` printing `AUDIT CHAIN VERIFIED · 12,481 events · replay equality PASS`.

## Guardrails
No business logic here. No knowledge of ladders, channels or models. `domain/` imports nothing from the project.

## Cut line
None.

## Prompt seed
> Read `context/phase-01-domain-core.md` and §5 of `docs/03-ARCHITECTURE.md`. Implement the event store and domain models. `EventStore.append` must be the only way case state changes — add an architecture test that fails if any module outside `audit/` writes to `cases`. Write the replay-equality and tamper-detection tests first.

## Commit
`feat(audit): append-only event store with hash chain and replay` · `Phase: 01-domain-core` · tag `phase-01`
