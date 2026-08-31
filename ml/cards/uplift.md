# Model card — uplift (X-learner)

## What it does
Estimates tau(case) = P(recover \| treated) - P(recover \| untreated) per FR-3.3, via
an X-learner (ADR-0007) over two channel-agnostic LightGBM base models (control-arm
`mu0`, treated-arm `mu1`), then two regressors on the imputed treatment effects
(`tau0` fit on control-arm residuals, `tau1` on treated-arm residuals), combined as
τ(x) = 0.5·tau0(x) + 0.5·tau1(x) — 0.5 because cohort assignment in this batch is
an unweighted coin flip, so that's the real treatment propensity g(x). `mu0`'s
reported/exposed predictions are isotonic-calibrated (`mu0_calibrator`, fit on a
held-out control-arm validation split) before anything downstream sees them —
`tau0`/`tau1`'s internal imputed-residual training step uses `mu0`/`mu1`'s raw
scores, the standard narrower scope for that specific step.

Segments each case using `mu0` (self-heal probability) and τ together:
`sleeping_dog` (τ < -0.02) → `sure_thing` (mu0 ≥ 0.6) →
`lost_cause` (τ ≤ 0.05) → else `persuadable`.

## Data
16800 train / 3600 val / 3600 test cases
(seed 20260303), stratified by cohort, outcomes bootstrapped exactly
as in `ml/cards/propensity.md`.

## Metrics (held-out test set)
- **Qini coefficient: 47.3169** (gate: > 0) — model targeting
  beats random targeting by this much cumulative incremental recovery.
- **Uplift at top 20%:** 0.3270 — the incremental recovery
  rate the model would capture by only acting on its top-scored fifth of cases.
- **Agreement with the generator's ground-truth τ (Spearman): 0.4594**
  — the *only* place ground truth is used post-training: validating that the
  model's ranking resembles the true, unobservable-in-production uplift.
- Qini curve: `ml/artifacts/uplift/qini_curve.png`

## Segment distribution (test set)
| Segment | Count |
|---|---|
| persuadable | 2491 |
| sure_thing | 415 |
| lost_cause | 397 |
| sleeping_dog | 297 |

## Known failure modes
- **X-learner, not a causal forest.** ADR-0007's explicit tradeoff: this is
  transparent and fast to train, but less robust to complex treatment-effect
  heterogeneity than a causal forest would be. The fallback if this had proven
  unstable was a documented heuristic (treated propensity minus self-heal prior),
  never shipped as if it were a trained model — it wasn't needed here.
- **Channel-agnostic by construction** (see `ml/cards/propensity.md`'s note on the
  same tradeoff) — this τ is "does acting at all help", not "does acting via
  channel X help"; channel selection is the bandit's job (Phase 06).
- **The Spearman agreement number is a validation diagnostic, not a training
  signal** — ground truth never entered any `.fit()` call in this script, only
  the final correlation check. A future reader should not expect this number in
  production, where no such ground truth will exist to check against.
- **Same cold-start and bootstrapped-outcome limitations as the propensity models.**
