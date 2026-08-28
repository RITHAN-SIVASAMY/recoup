# Phase 04 · Policy engine

**Day 4, first half · The differentiator judges will probe hardest.**

## Mission
Rules as versioned data. A pure evaluator returning ALLOW / DENY / REQUIRE_APPROVAL with a rule ID. Property-based invariant tests that make violations impossible rather than unlikely.

## Why judges care
*"Compliant escalation, stopping rules"* is half the track bar. Most teams will write `if attempts > 3: stop`. Policy-as-code with Hypothesis invariants is the single clearest signal of fintech engineering maturity in the whole repository.

## Read first
`docs/01-FRD.md` FR-5, FR-6 · `docs/03-ARCHITECTURE.md` §7 · `docs/06-COMPLIANCE-MATRIX.md` · `docs/adr/0004-policy-as-code.md`

## Build
- [ ] `policies/regulatory.yaml` — quiet hours, consent, opt-out propagation, mandate cadence and never-retry causes, pre-debit notice, AFA threshold, contact-fatigue cap. **Separate file, privileged, not merchant-editable**
- [ ] `policies/ladders.yaml` — per-root-cause escalation ladders with `forbidden_actions`
- [ ] `policies/merchant/demo.yaml` — thresholds, caps, costs, margin, EV floor
- [ ] `policy/loader.py` — parse, validate against a schema, content-hash into `policy_version`, hot reload in dev
- [ ] `policy/evaluator.py` — **pure, sync, no I/O**: `evaluate(case, action, ctx) -> Verdict`, short-circuiting in the fixed order: kill switch/exposure → cohort → regulatory → stopping rules → fatigue budget → ladder validity → approval thresholds → ALLOW
- [ ] `policy/simulator.py` — replay historical events through a candidate policy and diff the outcomes
- [ ] `tests/property/` — **write these first**:
  - contacts ≤ max_contacts, always
  - no contact after opt-out, ever, across all cases
  - control cohort ⇒ zero actions
  - `mandate_revoked` ⇒ `retry_charge` never appears
  - one idempotency key ⇒ at most one executed action
  - every executed action has a preceding logged ALLOW or APPROVED verdict
- [ ] Quiet-hours unit tests across timezone edges, DST transitions and midnight wraps
- [ ] Every DENY writes `policy.denied` with the rule ID, so the compliance view is a query, not a special log

## Key interface
```python
def evaluate(case: Case, action: ProposedAction, ctx: PolicyContext) -> Verdict:
    """Pure. Deterministic. No I/O, no LLM, no clock access — ctx carries `now`."""
```

## Definition of done
All invariants green; at least three demonstrable blocks (quiet hours, opt-out, revoked mandate) each naming its rule ID; an architecture test proving no execution path exists without a logged verdict.

## Demo hook
Compliance view listing blocked actions, each with its rule ID and a plain-English reason.

## Guardrails
Any rule that cannot be expressed in YAML is escalated to a human decision and an ADR — never hardcoded quietly. The evaluator never reads the clock itself; `ctx.now` is injected so tests can freeze it.

## Cut line
The policy simulator may slip to Phase 11. The evaluator and its invariants may not.

## Prompt seed
> Read `context/phase-04-policy-engine.md` and §7 of `docs/03-ARCHITECTURE.md`. Implement the policy engine as a pure function over YAML policy. Write the Hypothesis invariant tests **first**, then make them pass. Escalate to me any rule you cannot express in YAML.

## Commit
`feat(policy): policy-as-code evaluator with invariant tests` · `Phase: 04-policy-engine` · tag `phase-04`
