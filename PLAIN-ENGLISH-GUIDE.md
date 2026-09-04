# Recoup, in Plain English

**A companion to the real docs, not a replacement for them.** `docs/` is the authoritative
specification — if this guide and `docs/` ever disagree, `docs/` is right and this file is
stale and should be fixed. This exists purely so the jargon in the real documents doesn't get
in the way of understanding what's actually being built and why.

---

## 1. What Recoup actually is, in one paragraph

Some of the money customers try to pay a merchant never arrives — a bank OTP times out, a card
expired, a subscription payment silently stopped renewing, someone got distracted at checkout,
or a business customer just hasn't paid an invoice yet. Recoup watches for all of these,
figures out *why* the money didn't arrive, decides whether it's even worth chasing, and — only
if it's worth it and allowed by the rules — nudges the customer through the right channel
(text, WhatsApp, email, a one-tap payment link, or a phone call) to fix it. Then it proves, with
real statistics rather than a vibe, how much of the recovered money it actually *caused* versus
money that would have shown up anyway.

The one sentence version, taken straight from the real README because it's the whole idea:

> **The LLM proposes. Deterministic code disposes. The log remembers everything.**

Meaning: the AI is allowed to draft a message or explain something, but it is never allowed to
decide anything or press send. A separate, boring, rule-based piece of code makes every real
decision, and every single thing that happens is written down permanently.

---

## 2. The story version

Picture a merchant, Priya. Every month, out of every ₹100 customers *try* to pay her, ₹8–15
never arrives — not because people don't want to pay, but because something got in the way.
Today she has three bad options: ignore the leak, hire someone to chase it by hand (which
doesn't scale), or install a generic reminder tool that blasts the same SMS to everyone,
annoys her best customers, ignores India's do-not-disturb rules, and can't tell her whether it
actually made a difference or the customer would've paid anyway.

Recoup is built to be the fourth option: something that knows *who* to leave alone, *what* the
right fix is for each specific person, whether chasing them is even worth the ₹3–5 it costs,
and can prove its own impact honestly afterward.

---

## 3. The four ways money leaks (and why they're not the same problem)

| What happened | Example | The right fix |
|---|---|---|
| **A one-time payment failed** | Bank declined it, OTP page timed out, no money in the account, card expired | Retry at the right time, or nudge on the right channel — never a blind retry |
| **Checkout abandonment** | Customer got distracted before paying; there's no "failure" at all, they just left | A quick, low-friction reminder with a direct link back |
| **A subscription payment failed** | UPI Autopay / e-mandate renewal broke — could be a temporary glitch, or the customer cancelled it, or there's no money | If it's a real cancellation, retrying is **not allowed** — has to ask the customer to re-authorize instead |
| **A B2B invoice is overdue** | A business customer just hasn't paid yet | A polite reminder that gets firmer over time, with a human approving anything serious |

Treating all four the same way ("payment failed → send a reminder") is the mistake almost every
generic bot makes. It's also how you accidentally break real rules (like retrying a cancelled
subscription) or double-charge someone from a duplicate webhook.

---

## 4. How it works, step by step

Think of a single failed payment moving through six stages, left to right:

```
 1. INGESTION        2. UNDERSTANDING      3. ECONOMICS        4. POLICY            5. EXECUTION         6. MEASUREMENT
 "what happened?"    "why did it happen,   "is it worth        "are we allowed      "do the thing,       "did it actually
                      and would nudging     doing?"             to do it?"           safely"              work?"
                      them even help?"
```

**1. Ingestion** — Recoup hears about the failure (a webhook from Razorpay, a poller checking
subscriptions, an abandoned-checkout tracker, an imported list of overdue invoices), makes sure
it hasn't already seen this exact event before (no double-processing the same webhook), and
turns it into one standard record called a **Case**.

**2. Understanding** — A model looks at the case and works out the *root cause* (bad OTP?
expired card? no funds? cancelled mandate?). Then, separately, it estimates something more
subtle: not just "will this customer pay?" but **"will this customer pay *because we nudged
them*, versus paying anyway?"** That second question is the one almost nobody bothers to ask,
and it's the difference between actually helping and just taking credit for what would've
happened regardless.

**3. Economics** — Every message costs real money, and every extra contact costs a bit of the
customer's patience. So before doing anything, Recoup does the arithmetic: expected value =
(chance our action makes a difference) × (amount at risk) − (cost of the message) − (cost of
annoying them again). If the sum comes out negative, it stops right there and does nothing —
and it writes down *why*, rather than silently giving up.

**4. Policy** — Even if the economics say "worth it," a separate, much stricter layer checks
whether it's actually *allowed*: Is it within permitted contact hours? Did the customer opt
out? Have we already contacted them too many times this month? Is this the kind of failure
where retrying is illegal (a cancelled subscription)? Does this cost enough that a human needs
to approve it first? This layer answers with exactly one of three words — **ALLOW**, **DENY**,
or **REQUIRE_APPROVAL** — and always names the specific rule that produced the answer. This is
also the part of the codebase built in Phase 04 (see §7 below).

**5. Execution** — If (and only if) the policy layer said ALLOW, the actual message goes out —
SMS, WhatsApp, email, or a voice call — usually through a self-serve link that already knows
what went wrong and offers the one-tap fix. Even after approval, there's a short pause before
anything actually sends, so a mistake can still be pulled back.

**6. Measurement** — This is the part that makes the numbers trustworthy: a small group of
cases is deliberately left alone on purpose (the **control group**), so at the end Recoup can
compare "customers we nudged" against "customers we didn't" and report the *honest* difference,
not just a raw total that includes people who would've paid anyway.

Everything that happens at every stage gets permanently written to a tamper-evident log before
anything else happens — that log is the actual source of truth; everything else is just a view
of it.

---

## 5. Jargon buster

The real docs use precise technical language on purpose (so nothing is ambiguous), which makes
them hard to skim. Here's what the recurring terms actually mean.

| Term | Plain-English meaning |
|---|---|
| **Root cause** | The specific reason a payment failed (expired card, no funds, OTP timeout, etc.), not just "it failed" |
| **Propensity** | The probability a customer resolves the issue **on their own**, with no help |
| **Uplift** | The *extra* probability a customer resolves it **because we nudged them** — propensity-with-a-nudge minus propensity-without-one. This is the number that actually matters, not raw propensity |
| **Persuadable / sure thing / lost cause / sleeping dog** | Four buckets uplift sorts customers into: persuadable = nudging genuinely helps; sure thing = they'll pay regardless, don't bother; lost cause = nothing will help, don't bother; sleeping dog = nudging them actually makes things *worse* (e.g. annoys them into churning) |
| **EV (expected value)** | The arithmetic of "is this action worth doing" — uplift × amount at risk, minus what the action costs, minus a penalty for contacting someone too often |
| **Cohort / control / treatment** | The customers split at random into two groups: **treatment** (Recoup is allowed to act on them) and **control** (deliberately left untouched, forever, so there's something honest to compare against) |
| **Incremental recovery** | The recovered amount from the treatment group *minus* what the control group recovered on its own — the actual, honest impact, as opposed to a raw total that flatters itself |
| **Policy-as-code** | The rules that govern what Recoup is allowed to do are written as plain YAML config files, not buried as scattered `if` statements in the code — so a rule can be read, audited, and changed without touching program logic |
| **Ladder** | The specific, ordered sequence of steps for one root cause (e.g. "retry once, then wait 6 hours, then send an SMS, then stop") |
| **Quiet hours** | The legally/socially permitted window to contact someone (Recoup defaults to 09:00–20:00 India time) |
| **Contact fatigue** | The rule that caps how many times any one customer can be contacted in a rolling window, regardless of how promising they look |
| **Mandate** | India's UPI Autopay / e-mandate system for recurring/subscription payments — has its own strict rules (e.g. you may **never** silently retry a cancelled mandate; you must ask the customer to re-authorize instead) |
| **AFA (Additional Factor of Authentication)** | Above a certain rupee amount, an automated retry isn't allowed at all — it legally needs the customer to actively re-authorize |
| **Idempotency key** | A fingerprint computed from "this exact action, for this exact case, at this exact step" that guarantees the same action can never accidentally execute twice — the fix for "a duplicate webhook shouldn't double-charge anyone" |
| **Kill switch** | One global flag that, when flipped on, makes the policy engine refuse *everything*, instantly |
| **Exposure cap** | A hard ceiling on total ₹ a merchant's account can have "in flight" across all pending actions at once |
| **Verdict** | The formal answer the policy engine gives for one proposed action: ALLOW, DENY, or REQUIRE_APPROVAL, plus the exact rule ID and reason that produced it |
| **Staged action / undo window** | Even an approved action doesn't fire instantly — it sits for a short window where it can still be cancelled, so a mistake is recoverable |
| **Event sourcing** | Instead of just storing "the current state" of a case, Recoup stores *every single fact that ever happened to it*, in order, forever. Current state is always just a replay of that history — never edited directly |
| **Hash chain** | Each recorded fact includes a fingerprint of the fact before it, so if anyone ever tampered with old history, replaying the chain would immediately reveal a break |
| **Replay** | Rebuilding "what is currently true about this case" purely by re-reading its full history from the start — used to prove the log and the live state never silently drifted apart |
| **Calibration** | Making sure that when a model says "70% chance," that's genuinely true about 70% of the time — not just a score that *ranks* things correctly. Matters because the economics math treats these numbers as real probabilities |
| **Brier score / Qini curve** | Two specific scoring methods used to check a model is honest: Brier score for "are these probabilities well-calibrated," Qini for "does the uplift model actually separate persuadable customers from everyone else" |
| **Property-based test / invariant** | Instead of testing one specific example, generate hundreds of random, weird inputs and assert a rule can *never* be broken by any of them (e.g. "a customer who opted out is never contacted, no matter what") — much stronger proof than a handful of example tests |
| **Import-linter contract** | An automated rule that certain code layers are only allowed to depend on certain other layers (e.g. the policy engine may only depend on shared data types, never on anything that talks to a database) — enforced by a tool, not just a convention people are trusted to follow |
| **Grounded Q&A** | The chat feature that answers "why did this happen?" — it's only allowed to answer using facts it can point to in the actual log, and must say "I don't know" rather than invent something plausible-sounding |
| **Chaos suite** | A test suite that deliberately breaks things on purpose (duplicate events, a provider going down, a crash mid-action) to prove nothing gets lost, duplicated, or double-charged when things go wrong |
| **ADR (Architecture Decision Record)** | A short written note explaining a deliberate design choice and why an alternative was rejected — kept so nobody has to guess "why is it built this way?" later |
| **Gate** | The checklist a phase of the build must pass — tests green, types check, architecture rules enforced — before it's allowed to be marked done |

---

## 6. The ten rules, in plain English

The real ground rules (`CLAUDE.md`) are the actual authority; this is just a faster read of them.

1. **The AI never presses the button.** It can draft a message or explain something — it can never send, charge, or decide anything.
2. **Nothing happens off the record.** Every single change is written to the permanent log first.
3. **Rules live in config files, not scattered code.** A rule written as Python `if` statements instead of YAML config is treated as a bug.
4. **Everything is reproducible.** Same seed in, same result out — no test that depends on "whatever time it happens to run."
5. **Money is exact.** Rupees are stored precisely (never as an imprecise decimal/float) — no rounding drift.
6. **Every external call can fail, and is expected to.** Nothing assumes a network call, a text send, or an AI call always succeeds.
7. **Tests are part of the actual deliverable**, not an afterthought — especially tests that make a bad outcome *impossible*, not just untested.
8. **Everything is strictly typed**, so a whole category of "wrong shape of data" bugs gets caught before the code even runs.
9. **Metrics are never allowed to lie by omission.** If a result isn't statistically significant, the system says so — it can't quietly present a coin-flip as a win.
10. **Commits are small and mean one thing each.**

---

## 7. Where things actually live (folder map, plain terms)

| Folder | In plain terms |
|---|---|
| `domain/` | The basic shared vocabulary (what a "Case" is, what a "Verdict" is) — has zero dependencies on anything else, so everyone can safely depend on it |
| `ingestion/` | Hears about failures from the outside world and turns them into Cases |
| `understanding/` | The models: root cause, propensity, uplift, segments |
| `economics/` | The cost/benefit arithmetic (EV engine) |
| `policy/` | The rulebook and the pure, no-side-effects code that checks a proposed action against it |
| `execution/` | Actually carries out an allowed action, and glues the policy verdict to the permanent log |
| `voice/` | The bounded phone-call flow |
| `measurement/` | Control groups, statistics, the honest-impact report |
| `audit/` | The permanent tamper-evident log itself, and the "explain what happened" chat |
| `llm/` | Everything involving Claude — drafting, classifying-assisting, explaining — kept separate because it's the one layer that's explicitly *not* trusted to decide anything |
| `policies/*.yaml` | The actual rules, as data, not code |
| `docs/` | The real specification (a separate linked repo, `recoup-docs`) — the authority this guide summarizes |
| `context/` | Short per-phase build briefs used while building each phase |

---

## 8. Where things stand right now

The build followed its own 13-phase plan (`docs/04-EXECUTION-PLAN.md`), one phase at a time,
each with its own tests and a gate that had to go green before moving on. All thirteen are done.

| Phase | What it delivers | Status |
|---|---|---|
| 00 | Repo scaffold, tooling, CI | ✅ done |
| 01 | The permanent event log (hash-chained, replayable) | ✅ done |
| 02 | Ingestion from all four leak sources, deduped | ✅ done |
| 03 | Root-cause classifier, propensity, uplift models | ✅ done |
| 04 | Policy engine — the rulebook and the ALLOW/DENY/REQUIRE_APPROVAL evaluator | ✅ done |
| 05 | Economics — the EV engine | ✅ done |
| 06 | Execution — channels, staging, real dispatch (simulated) | ✅ done |
| 07 | Self-serve recovery page | ✅ done |
| 08 | Voice (Hinglish call flow), promise-to-pay capture | ✅ done |
| 09 | Grounded Q&A over the audit log | ✅ done |
| 10 | Measurement — control groups, statistics, `make demo` orchestration | ✅ done |
| 11 | Merchant dashboard (work queue, approvals, kill switch, live chaos control) | ✅ done |
| 12 | Final polish, README, CI, submission | ✅ done |

Two things worth knowing that aren't in the phase table itself: the canonical `make demo`
batch currently prints an **honest null result** — real revenue at risk, real cost accounting,
but not enough evidence at this batch size to claim the incremental recovery is real rather
than noise, and the system says so instead of hiding it (see the README's "The proof"
section). And a real bug shipped and got caught along the way — `domain/ids.py` minted case
IDs from wall-clock time even inside the supposedly-seeded demo batch, so "the same seed"
silently produced a different result every run until it was found and fixed. Both are logged
honestly in the incident log below, not smoothed over.

For the honest, detailed version of "what broke and how it got fixed" while building each
phase, see `docs/09-INCIDENT-LOG.md` — nothing in it is sanitized.

---

## 9. If you want the real thing

This guide simplifies on purpose and will go stale as the build progresses — treat it as a way
in, not a citation. When you need the precise, authoritative version:

| Question | Read |
|---|---|
| "What exactly must it do, refuse to do, and prove?" | `docs/01-FRD.md` |
| "Why does this problem matter, and why doesn't 'just ask an AI' solve it?" | `docs/02-PROBLEM-AND-DIFFERENTIATION.md` |
| "How is it actually put together?" | `docs/03-ARCHITECTURE.md` |
| "What's the build plan and tech stack?" | `docs/04-EXECUTION-PLAN.md` |
| "How is every reported number produced?" | `docs/05-EVALUATION-PROTOCOL.md` |
| "Which rule maps to which config, code, and test?" | `docs/06-COMPLIANCE-MATRIX.md` |
| "What broke, and how was it fixed?" | `docs/09-INCIDENT-LOG.md` |
