# Phase 10 · Measurement

**Day 7, first half · The number the whole submission rests on.**

## Mission
Produce an incremental recovered-revenue figure that survives interrogation: randomized, stratified, significance-tested, interval-reported, and reproducible.

## Why judges care
*"Show measured money recovered"* is the literal bar. Most submissions will report a raw, uncontrolled number. This is the one figure a judge cannot poke a hole in — provided we implement it exactly as pre-registered and report the null honestly if that is what we get.

## Read first
`docs/05-EVALUATION-PROTOCOL.md` (all of it) · `docs/01-FRD.md` FR-13

## Build
- [ ] `measurement/cohort.py` — stratified assignment at case creation by seeded hash of `case_id + salt`, stratified on (root cause × amount band × segment); immutable, recorded as `case.cohort_assigned` **before** any scoring
- [ ] Control integrity: an invariant test proving zero actions attach to a control case; a DB-level guard as well
- [ ] Exclusions: cases above the merchant value cap and legal-risk-flagged cases are always treated; exclusions logged and counted
- [ ] `measurement/holdout.py` — adaptive controller with alpha-spending (O'Brien-Fleming style); decay toward a 5% floor once the effect is established; automatic re-expansion if lift drifts outside its band; **every look is logged**
- [ ] `measurement/stats.py` — lift, incremental ₹, two-proportion z-test, 95% CI, MDE at 80% power
- [ ] `measurement/cuped.py` — variance reduction on pre-period payment reliability; the unadjusted number is always reported alongside
- [ ] Breakdowns by root cause, channel, segment, value band — including negative lift where it occurs
- [ ] `measurement/report.py` — the headline block exactly as specified in `05-EVALUATION-PROTOCOL.md` §9, plus JSON and Markdown export
- [ ] `make demo` prints the headline block; two seeded runs are byte-identical

## Definition of done
Headline block printed and reproducible. If the lift is not significant, the output says so in words, next to the MDE.

## Demo hook
The headline block, and the holdout-decay chart showing the control group shrinking as evidence accumulated.

## Guardrails
No code path may make a non-significant result look significant. No post-hoc metric selection — the primary metric is fixed in the protocol document, which is committed before results exist. Do not "fix" a disappointing result by changing the analysis.

## Cut line
CUPED and the adaptive controller may degrade to a fixed 20% holdout with a plain z-test. **The control group itself is never cut.**

## Prompt seed
> Read `context/phase-10-measurement.md` and all of `docs/05-EVALUATION-PROTOCOL.md`. Implement the measurement engine exactly as pre-registered. If the lift is not significant at the batch size run, the output must say so explicitly. Do not add any code path that could make a null look like a win.

## Commit
`feat(measurement): incremental recovery with adaptive holdout and CUPED` · `Phase: 10-measurement` · tag `phase-10`
