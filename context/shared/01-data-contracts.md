# Shared context · Data contracts

These shapes are fixed. Changing one is a spec change, not a refactor.

## CaseEvent (append-only, source of truth)

```python
class CaseEvent(BaseModel):
    event_id: ULID
    case_id: ULID
    seq: int                      # per-case, gapless, starts at 1
    occurred_at: datetime         # UTC, provider time where known
    recorded_at: datetime         # UTC, our clock
    actor: Actor                  # system | model:<name>@<version> | human:<id> | provider:<name>
    event_type: str               # dotted, past tense: case.created, action.staged, policy.denied
    payload: dict                 # canonical JSON, schema per event_type
    policy_version: str | None    # content hash of the policy in force
    model_versions: dict[str, str] | None
    prev_hash: str
    hash: str                     # sha256(prev_hash ‖ canonical(payload) ‖ seq ‖ occurred_at)
```

**Event type vocabulary** (extend deliberately, never ad hoc):
`case.created` · `case.classified` · `case.scored` · `case.cohort_assigned` · `ev.computed` ·
`policy.evaluated` · `policy.denied` · `approval.requested` · `approval.granted` · `approval.rejected` ·
`action.staged` · `action.cancelled` · `action.sent` · `action.delivered` · `action.engaged` · `action.suppressed_duplicate` ·
`ptp.captured` · `ptp.kept` · `ptp.broken` · `payment.recovered` · `case.stopped` · `case.abandoned_uneconomic` ·
`case.exception` · `event.duplicate_suppressed` · `killswitch.engaged`

## Verdict (policy engine output — pure, no I/O)

```python
class Verdict(BaseModel):
    decision: Literal["ALLOW", "DENY", "REQUIRE_APPROVAL"]
    rule_id: str                  # e.g. "REG-COMM-01"
    policy_version: str
    reason: str                   # human-readable, shown in the UI
    obligations: list[str] = []   # e.g. ["stage_for_60s", "log_pii_redacted"]
```

## ProposedAction

```python
class ProposedAction(BaseModel):
    action_type: Literal["retry_charge","send_message","send_reauth_link","voice_call",
                         "draft_formal_notice","stop"]
    channel: Channel | None
    ladder_step: int
    scheduled_for: datetime
    estimated_cost_inr: Decimal
    expected_value_inr: Decimal
```

## Rules

- Money is `Decimal` with 2dp, or integer paise. Never `float`.
- Times are timezone-aware UTC. `Asia/Kolkata` appears only at display and quiet-hours evaluation.
- IDs are ULIDs (sortable by creation time).
- Canonical JSON = sorted keys, no whitespace, UTF-8, `Decimal` as string. One implementation, in `domain/canonical.py`, used by both the hash chain and the dedupe key.
- Every Pydantic model at a boundary sets `model_config = ConfigDict(frozen=True, extra="forbid")`.
