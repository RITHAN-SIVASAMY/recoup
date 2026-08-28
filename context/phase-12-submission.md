# Phase 12 · Submission

**Day 8 · Convert a working system into an accepted, memorable submission.**

## Mission
Deploy, record, document, verify, submit — with a day of margin.

## Why judges care
This is the only phase they see directly. A repo that does not build, a video that runs long, or a number without an interval undoes a week of good engineering.

## Read first
`docs/08-SUBMISSION-CHECKLIST.md` · `docs/07-DEMO-SCRIPT.md` · `docs/09-INCIDENT-LOG.md`

## Build
- [ ] **Deploy**: API + worker (Railway/Fly), Postgres (Neon), Redis (Upstash), web (Vercel); seeded demo batch loaded; read-only demo credentials in the README; a spend cap on the Anthropic key; a **test mode / synthetic data** banner on every public page
- [ ] **README**: one-paragraph pitch → headline numbers **with CI** → 60-second quickstart (`git clone --recurse-submodules` in the first three lines) → architecture diagram → live demo link → demo GIF → "what we deliberately did not build" → honest limitations
- [ ] **Video**: record per the demo script; hard cut at 4:50; captions on the key numbers; upload unlisted; test the link in an incognito window
- [ ] **Incident log**: complete `docs/09-INCIDENT-LOG.md` honestly, including the running summary table and the Day-8 reflection prompts
- [ ] **Verify reproducibility on a clean machine**: fresh container → clone → `make setup` → `make demo` → same headline numbers. Do not assume this; run it
- [ ] Final `make verify`, `make chaos`, full CI green; all phase tags pushed; submodule pointer bumped; both repos public
- [ ] Rehearse 30-second answers to the five judge questions in `docs/08-SUBMISSION-CHECKLIST.md` §6
- [ ] Submit on razorpay.com/buildathon with repo, video and architecture-doc links, plus the resume

## Definition of done
A stranger clones the repo, runs `make demo`, and sees the same headline numbers. The video is under five minutes. The submission is in with margin.

## Guardrails
Do not add features on Day 8. Do not report a raw number as the headline. Do not claim production performance from synthetic data. Do not claim regulatory certification — *alignment by design, verification required*.

## Prompt seed
> Read `context/phase-12-submission.md` and `docs/08-SUBMISSION-CHECKLIST.md`. Write the final README from the actual output of `make demo` — every number in it must be generated, not typed. Then verify a clean-machine clone-to-demo run and report exactly what a stranger would experience.

## Commit
`docs(submission): final README, deployment and submission artifacts` · `Phase: 12-submission` · tag `v1.0.0`
