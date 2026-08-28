# Phase 06 · Execution and channels

**Day 5, first half · The first full end-to-end recovery.**

## Mission
Make actions actually happen — safely, idempotently, deterministically, and for free.

## Why judges care
This is where the pipeline becomes a product. It is also where duplicate-suppression and circuit-breaking become demonstrable rather than theoretical.

## Read first
`docs/01-FRD.md` FR-9 · `docs/adr/0006-simulator-first-channels.md`

## Build
- [ ] `execution/ports.py` — `ChannelPort` protocol: `send(rendered_message, idempotency_key) -> DeliveryReceipt`
- [ ] `execution/adapters/simulator.py` — seeded, deterministic, per-segment open/click/convert curves and realistic latency; the **default** adapter
- [ ] Optional live adapters behind a flag: `twilio_sms.py`, `whatsapp_cloud.py`, `resend_email.py`
- [ ] `execution/renderer.py` — templates with a strict contract (sender identity, opt-out affordance, category); Claude drafts copy into the template's variable slots, schema-validated, length-capped, PII-redacted, prohibited-claims checked
- [ ] `execution/dispatcher.py` — the single choke point: verdict check → idempotency guard → stage → send → delivery events. **The only module that touches an adapter**
- [ ] `execution/bandit.py` — Thompson sampling (Beta posteriors per `(segment, channel, hour_bucket)`), restricted to policy-permitted, EV-cleared arms; posteriors in Redis, updated on outcome events
- [ ] Channel fatigue: suppress a channel ignored twice consecutively; per-channel cooldowns
- [ ] Resilience: timeouts, bounded retry with jitter, per-provider circuit breakers; failed sends never mutate state optimistically
- [ ] Delivery-state events: `action.sent` → `action.delivered` → `action.engaged` / `bounced` / `failed`

## Definition of done
A treatment case moves ingest → diagnose → score → EV → policy → stage → send → engage → recover end-to-end in the simulator. A property test proves the bandit can never select a policy-denied arm.

## Demo hook
`make demo` running the full batch with the live SSE stream showing cases resolving.

## Guardrails
The dispatcher is the only path to an adapter. The bandit chooses **among permitted arms only** — it never widens the action set. Generated copy never bypasses the template contract.

## Cut line
Live adapters are optional. The bandit can degrade to channel-fit + fixed timing, documented as such in the UI.

## Prompt seed
> Read `context/phase-06-execution-channels.md`. Implement the channel port, the deterministic simulator, the dispatcher choke point and the constrained bandit. Add a property test asserting the bandit's chosen arm is always a member of the policy-permitted set.

## Commit
`feat(execution): channel ports, simulator, dispatcher and constrained bandit` · `Phase: 06-execution-channels` · tag `phase-06`
