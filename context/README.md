# Context files

One file per build phase. Each Claude Code session should start by reading:

1. `../CLAUDE.md` (loaded automatically)
2. every file in `shared/`
3. the single `phase-NN-*.md` for the phase being built

Then restate the objective, the definition of done, and the implementation plan **before writing code**.

| Phase | File | Day | Objective in one line |
|---|---|---|---|
| 00 | [foundation](phase-00-foundation.md) | 1 | A repo that is impossible to make messy later |
| 01 | [domain core](phase-01-domain-core.md) | 1 | Event store, hash chain, replay, idempotency |
| 02 | [ingestion](phase-02-ingestion.md) | 2 | Four sources in, one Case out, nothing ever lost |
| 03 | [understanding](phase-03-understanding.md) | 3 | Calibrated diagnosis and uplift-based targeting |
| 04 | [policy engine](phase-04-policy-engine.md) | 4 | Rules as data, invariants as tests |
| 05 | [economics & authority](phase-05-economics-and-authority.md) | 4 | Learn to say "not worth it" and "ask a human" |
| 06 | [execution & channels](phase-06-execution-channels.md) | 5 | Actions happen — safely, idempotently, for free |
| 07 | [recovery microsite](phase-07-recovery-microsite.md) | 5 | The thing a judge touches with their thumb |
| 08 | [voice & PTP](phase-08-voice-and-ptp.md) | 6 | Hinglish call with a captured promise |
| 09 | [grounded explainability](phase-09-grounded-explainability.md) | 6 | The chat layer that refuses to lie |
| 10 | [measurement](phase-10-measurement.md) | 7 | The number the submission rests on |
| 11 | [dashboard & chaos](phase-11-dashboard-and-chaos.md) | 7 | Make it visible, then break it on purpose |
| 12 | [submission](phase-12-submission.md) | 8 | Deployed, recorded, documented, submitted |

Every phase file follows the same shape: **Mission · Why judges care · Read first · Build · Interfaces · Definition of done · Gate command · Demo hook · Guardrails · Cut line · Commit.**
