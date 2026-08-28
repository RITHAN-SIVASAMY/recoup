# Phase 11 · Dashboard, what-if and chaos

**Day 7, second half · Make every differentiator visible in five seconds, then break it on purpose.**

## Mission
A dashboard that a judge can navigate without narration, and a chaos control that proves graceful failure live.

## Why judges care
The dashboard is the only part of the system they experience directly. And *"what broke and how you got out"* is an explicit evaluation question — answering it with a live demonstration beats answering it with an anecdote.

## Read first
`docs/01-FRD.md` FR-15, FR-16 §14 (acceptance criteria) · `docs/07-DEMO-SCRIPT.md` · `docs/adr/0008-nextjs-dashboard.md`

## Build

**Dashboard (Next.js)**
- [ ] Batch summary: at-risk ₹, **raw vs. incremental side by side**, CI, cost per ₹ recovered, ₹ saved by not acting, cases by state
- [ ] Work queue ranked by expected incremental value, each row with a one-line reason
- [ ] Approval queue with decision cards; working cancel inside the undo window; kill switch control
- [ ] Exception queue + DLQ view with truthful reasons
- [ ] Case timeline rendered directly from the event log, with policy verdicts, EV ledger, messages and outcomes inline
- [ ] Compliance view: blocked actions with rule IDs, opt-outs honoured, quiet-hours suppressions, mandate retries prevented
- [ ] Model transparency panel: confusion matrix, calibration curve, Qini curve, model cards
- [ ] Grounded Q&A panel with clickable citations
- [ ] Live SSE stream so the demo visibly runs
- [ ] What-if simulator: adjust approval threshold, holdout rate, contact caps, EV floor, channel costs → replay history → projected recovery, spend and contact volume

**Chaos**
- [ ] `tests/chaos/` scenarios: duplicate webhook, out-of-order events, malformed payload, provider 5xx, provider timeout, LLM timeout, LLM invalid schema, worker crash mid-action, clock skew, poisoned model output
- [ ] Each asserts: zero duplicate contacts, zero duplicate charge attempts, zero lost cases, a truthful exception entry
- [ ] "Break it" control in the demo UI that runs a chosen scenario live and shows the system absorbing it

## Definition of done
Every one of the 14 acceptance criteria in `docs/01-FRD.md` §14 is reachable in ≤2 clicks from the dashboard. All chaos scenarios pass and are demonstrable live.

## Demo hook
The chaos menu itself — few submissions will have one.

## Guardrails
Every number rendered with its uncertainty where one exists. No fake data in the UI, ever — if a panel has no data, it says so. The what-if simulator must be labelled as a projection, never as a measurement.

## Cut line
The what-if simulator UI drops first. The compliance view and the case timeline do not.

## Prompt seed
> Read `context/phase-11-dashboard-and-chaos.md` and §14 of `docs/01-FRD.md`. Build the dashboard so that each acceptance criterion is reachable in two clicks, and implement the chaos suite with a live "Break it" control. Generate API types from the OpenAPI schema rather than hand-writing them.

## Commit
`feat(web): merchant dashboard, what-if simulator and live chaos control` · `Phase: 11-dashboard-and-chaos` · tag `phase-11`
