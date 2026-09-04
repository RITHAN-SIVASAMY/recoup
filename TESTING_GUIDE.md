# Trying Recoup — a hands-on walkthrough

This is a practical guide to running Recoup locally and actually poking at every
part of it — not just reading about it. Fifteen minutes gets you a running
dashboard with real (synthetic) data; another fifteen gets you through every
feature worth seeing.

Everything here uses **synthetic, seeded data**. No real merchant, customer, or
payment is ever involved.

---

## 1. Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package/dependency manager)
- Node.js 20+ and npm
- Docker Desktop (for Postgres + Redis)
- An `ANTHROPIC_API_KEY` if you want the LLM-backed features (classification
  explanations, grounded Q&A, voice dialogue) to run live instead of in
  degraded/template mode — everything else works without one

## 2. One-time setup

```bash
git clone --recurse-submodules <repo-url>
cd recoup
cp .env.example .env        # fill in ANTHROPIC_API_KEY if you have one
make setup                  # installs deps, starts postgres+redis, runs migrations, installs web deps
```

## 3. Bring the stack up

Three processes, three terminals:

```bash
docker compose up -d postgres redis      # if make setup didn't leave them running
uv run uvicorn recoup.api.main:app --port 8000    # backend API + SSE stream
cd web && npm run dev                             # dashboard, http://localhost:3000
```

(`make run` does the API + worker + web together via Docker if you'd rather not
juggle terminals — slower to iterate with, but one command.)

## 4. Generate a batch

```bash
make demo
```

This runs 2,000 seeded synthetic cases end to end — ingestion, classification,
scoring, the recovery ladder, measurement — and prints a headline block like:

```
RECOUP · BATCH b_seed42_2000 · seed 42 · 2000 cases
At risk                        ₹ 17,36,12,265
Raw recovered (treated)        ₹ 4,92,11,755   ← overstates our impact
Incremental recovered          ₹ -51,79,409   (95% CI ₹ -1,29,40,473 – ₹ 25,81,655)
Lift                           -4.3 pp       z = -1.31, p = 0.1909   *** NOT SIGNIFICANT ***
...
Audit chain                    VERIFIED · replay equality PASS
```

It's deterministic — the same seed always reproduces the same numbers — and it
writes `data/reports/b_seed42_2000.{json,md}`, which is what the dashboard's
hero panel reads.

**A note on statistical honesty, so you don't think something's broken:**
you will very likely see `*** NOT STATISTICALLY SIGNIFICANT ***` in red when
you run this. That isn't a bug — the system refuses to claim a win it can't
back up (see rule 9 in `CLAUDE.md`). This synthetic data's true causal effect
sits close enough to zero that most seeds, even at 2,000 cases, land null; a
few land clearly positive, and that's the honest, expected shape of the
result, not a broken pipeline. Try a few different `SEED=` values to see the
spread yourself. Don't read a null result as failure — it's the same
refuse-to-oversell discipline that makes a *positive* result on this
dashboard worth trusting.

**A second note, on reproducibility:** the same seed always produces the same
case pool and the same treatment/control split — verified, not assumed (see
`docs/09-INCIDENT-LOG.md`'s incident on case-ID determinism). The exact ₹
figure can still drift a percent or two between two runs of the same seed,
because channel selection is a live Thompson-sampling bandit whose Redis-backed
state updates while ~2,000 cases process concurrently — a documented,
architecturally-bounded source of variance, not a bug being hidden. Don't
expect byte-identical output on a second run; do expect the same cases, the
same cohorts, and a statistically similar result.

Open **http://localhost:3000/dashboard**.

---

## 5. Touring the dashboard

### The hero panel (always visible, above the tabs)

- **Revenue at risk / raw recovered / incremental recovered** — the three
  numbers side by side is the whole pitch: raw recovered overstates impact,
  incremental is what a held-out control group proves actually happened.
- **Case resolution mix** — a proportional bar showing where every case ended
  up (recovered, pending, blocked by policy, exception, etc). Hover a segment
  for exact counts.
- Audit-chain and replay-equality badges — should always read green.

### Overview tab

- **Work queue** — every pending case ranked by expected value, highest first.
  Click a case ID to open its full event timeline.
- **Exception queue** — anything that needed a human. Should normally be
  empty or small; nothing is ever silently dropped here.

### Governance tab

- **Approval queue** — actions above the merchant's approval threshold, sitting
  and waiting for sign-off. Click **Approve** — it stages the action but keeps
  it cancellable for a window; click **Cancel before it sends** to prove the
  undo window is real.
- **Compliance** — every action policy has blocked, grouped by rule ID
  (quiet hours, opt-outs, mandate-retry prevention, control-cohort
  protection). This is the "it cannot become a spam engine" evidence.
- **Kill switch** (top right, always visible) — engage it and watch every
  in-flight staged action get cancelled, logged with actor and timestamp.
  Disengage to resume.

### Insights tab

- **Lift by segment** — a diverging bar chart breaking the incremental result
  down by root cause and uplift segment. Green = lift over control, pink/red
  = below control, faded + "n.s." = not statistically significant at that
  segment's sample size. This is real per-segment data most recovery-tool
  dashboards never show.
- **Model transparency** — each model's own confusion matrix / ROC / Qini
  curve, metrics, and a **known failure modes** list pulled straight from its
  model card. Nothing here is dressed up.
- **Ask the audit log** — grounded Q&A over the hash-chained event log. Try:
  - `"Why did we contact this account three times?"` on a case ID from the
    work queue — you should get an answer with clickable citations to
    specific event IDs.
  - `"Was this customer happy about the call?"` — this should come back
    **refused**, naming what would need to be logged for it to answer. A
    fabricated citation here fails CI (`tests/llm_eval/`), so a refusal is the
    correct, tested behavior, not a fallback.

### What-if & Chaos tab

- **What-if simulator** — replay the historical batch under different policy
  knobs (EV floor, channel cost, approval threshold, max contacts) and see how
  many cases would newly become contactable, newly need approval, etc. It
  deliberately never projects a ₹ number — a counterfactual isn't something a
  log replay can honestly supply.
- **Break it** — live failure injection against the running system, not a
  slide. Each scenario is a real async function in
  `src/recoup/chaos/scenarios.py`, not a mock:
  - `duplicate_webhook` — same webhook delivered 25 times → exactly one case,
    zero duplicate contacts
  - `out_of_order_events` — a stale contact attempt after the case already
    resolved
  - `provider_timeout` — the channel provider never responds → circuit breaker
  - `worker_crash_mid_action` — a worker dies right after sending → a fresh
    worker retries without duplicating the effect
  - `llm_timeout` / `llm_invalid_schema` — the model misbehaves → degraded
    mode, deterministic fallback
  - `clock_skew` — a provider timestamp arrives years off in either direction
  - `poisoned_model_output` — adversarial classifier input
  - (`malformed_payload` and `clock_skew` are proven by
    `tests/chaos/test_ingestion_chaos.py` instead of the live button — the UI
    marks these "Proven by test suite")

  Click any runnable one — you'll get a pass/fail narrative and a checklist of
  what was actually verified (zero duplicate contacts, zero duplicate charges,
  zero lost cases, a truthful exception-queue entry).

### Everywhere: the command palette

Press **⌘K** / **Ctrl+K** anywhere on the dashboard. Jump to any section, or
paste a case ID (from the work queue or exception queue) to go straight to its
timeline.

### Case timeline

Click any case ID. You get the full, ordered event history — classification
confidence, EV computation, every policy check with its rule ID, every action
staged/sent/cancelled — each with a collapsible raw payload. This is the same
data the grounded Q&A answers from, so you can sanity-check its citations by
hand.

---

## 6. Verifying integrity (not just the UI)

```bash
make verify   # hash-chain verification + replay equality — should print PASS
make chaos    # the full pytest chaos suite (not just the dashboard button)
make gate PHASE=11   # lint + types + tests + the phase-11 acceptance gate
```

## 7. If something looks broken

- **Docker containers unhealthy / `docker compose ps` errors** — Docker
  Desktop itself may need a restart (`docker info` hanging is the tell).
- **`make demo` fails with a Postgres `UniqueViolationError` on a second run
  with the same seed** — the local dev DB already has that seed's deterministic
  case IDs from a previous run (case IDs are seeded, on purpose — see
  `docs/09-INCIDENT-LOG.md`). This isn't a bug in the pipeline so much as
  local Postgres/Redis not being reset between demo runs; either use a
  different `SEED=`, or reset both local stores: `docker compose stop
  postgres redis && docker compose rm -f postgres redis && docker volume rm
  recoup_pgdata`, then `docker compose up -d postgres redis && uv run alembic
  upgrade head`. **Reset Redis too, not just Postgres** — a fixed case ID
  means the idempotency keys derived from it collide on a second run against
  stale Redis state, which silently blocks most actions instead of erroring.
  This wipes only local synthetic demo data, never anything real.
- **Dashboard shows "Could not load batch summary: Failed to fetch"** — the
  FastAPI backend on port 8000 isn't running or crashed; restart it.
- **`₹` prints as garbled characters or the CLI crashes with a
  `UnicodeEncodeError`** on Windows — already fixed (`src/recoup/cli.py`
  forces UTF-8 stdout); if you still hit it, run with
  `PYTHONIOENCODING=utf-8` set first.
