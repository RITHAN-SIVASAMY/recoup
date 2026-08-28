# Phase 05 · Economics, approval and reversibility

**Day 4, second half · The "would I put you near money" phase.**

## Mission
Teach the system to say *"not worth it"* and *"ask a human first"* — and to make every action cancellable before it becomes irreversible.

## Why judges care
Cost-awareness is rare even in commercial tools, and it converts restraint from laziness into intelligence. Reversibility is claimed by every agent project and specified by almost none.

## Read first
`docs/01-FRD.md` FR-4, FR-7 · `docs/06-COMPLIANCE-MATRIX.md` §3.3

## Build
- [ ] `economics/costs.py` — per-channel cost in ₹ (SMS, WhatsApp template, email, voice minute, human-review minute) from merchant config
- [ ] `economics/goodwill.py` — goodwill cost curve rising with contact count, higher for high-LTV customers
- [ ] `economics/ev.py` — `EV = uplift × amount × margin − channel_cost − goodwill_cost(n)`; every computation writes an `ev.computed` event with its inputs
- [ ] EV floor; when no candidate action clears it, terminate `abandoned_uneconomic` with the ledger recorded
- [ ] `economics/fatigue.py` — rolling per-customer contact budget across **all** cases (default 3 / 30 days)
- [ ] Merchant daily spend and contact-volume caps → queue rather than execute
- [ ] `execution/staging.py` — `StagedAction` with a configurable undo window (60s contact / 5min money); a scheduler promotes staged → sent; cancel is one call and writes `action.cancelled`
- [ ] `api/approvals.py` — approval queue + decision card payload: case, root cause + confidence, uplift, EV arithmetic, triggering rule, drafted copy, projected cost
- [ ] `execution/killswitch.py` — halts autonomous action, cancels in-flight staged actions, logs actor and timestamp
- [ ] Exposure cap enforcement (forces REQUIRE_APPROVAL once exceeded)
- [ ] Test: **every executed action was `staged` first** (property test)

## Definition of done
A case terminates `abandoned_uneconomic` with visible arithmetic; a staged action is cancelled inside its window and never sends; the kill switch cancels everything in flight and is logged with an actor.

## Demo hook
Live: approve a card, then cancel the staged action before it sends. Then hit the kill switch and watch the queue drain to zero.

## Guardrails
Nothing leaves the system without passing through a cancellable state. EV inputs come from calibrated probabilities only. Approvals and rejections are first-class audited events with actor identity.

## Cut line
None.

## Prompt seed
> Read `context/phase-05-economics-and-authority.md`. Implement EV gating and the staged-action buffer. Add a property test asserting that every executed action passed through `staged` first, and that no action executes while the kill switch is engaged.

## Commit
`feat(economics): EV gating, contact budgets, staged actions and kill switch` · `Phase: 05-economics-and-authority` · tag `phase-05`
