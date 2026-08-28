# Phase 07 · Self-serve recovery microsite

**Day 5, second half · The thing a judge touches with their own thumb.**

## Mission
Every message ends in a single-use link to a page that already knows what failed and offers exactly the right fix — completing in Razorpay test mode, live.

## Why judges care
It converts the submission from a dashboard into a product. A judge opening the link on their phone, paying in test mode, and watching the case flip to `recovered` on screen is the single most persuasive twenty seconds available to us.

## Read first
`docs/01-FRD.md` FR-12 · `docs/06-COMPLIANCE-MATRIX.md` SEC-DATA-04

## Build
- [ ] `execution/links.py` — HMAC-signed, single-use, expiring, non-enumerable tokens; reuse is refused with a friendly page, not a 500
- [ ] Public Next.js route `/r/[token]` — server-rendered, mobile-first, sub-second
- [ ] Cause-specific content and fix:
  - `card_expired_or_invalid` → update card
  - `insufficient_funds` → pay now / remind me later (customer-chosen date, honoured by the policy engine)
  - `otp_timeout_or_auth_abandon` → retry same method
  - `mandate_revoked` → re-authorize mandate
  - `checkout_abandonment` → resume cart
  - `receivable_overdue` → invoice detail + pay
- [ ] Razorpay **test-mode** Payment Links / Checkout integration; success webhook closes the loop
- [ ] One-tap opt-out and "remind me later", both written as case events and honoured by policy
- [ ] Page events (`view`, `method_switch`, `opt_out`, `paid`) fed back as case events and bandit/uplift signal
- [ ] Rate limiting; a visible **test mode / synthetic data** banner
- [ ] Accessibility: WCAG AA contrast, keyboard navigation, no dark patterns

## Definition of done
On a phone: open the link from a simulated SMS → complete a test-mode payment → the dashboard case flips to `recovered` over SSE within seconds. Reusing the link is refused.

## Demo hook
Exactly the above, filmed on a real phone in the pitch video.

## Guardrails
No PII in the URL. No enumerable IDs. The page never reveals data beyond that one case. A failed payment leaves the case recoverable, not stuck.

## Cut line
If Checkout integration fights back, fall back to hosted Payment Links. Do not lose the live-payment moment.

## Prompt seed
> Read `context/phase-07-recovery-microsite.md`. Implement signed single-use recovery links and the public recovery route with cause-specific fixes, backed by Razorpay test-mode payment links. Prove link reuse is refused and that the success webhook closes the case.

## Commit
`feat(recovery): signed single-use links and self-serve recovery page` · `Phase: 07-recovery-microsite` · tag `phase-07`
