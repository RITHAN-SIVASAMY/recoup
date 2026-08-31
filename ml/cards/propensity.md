# Model card — propensity (baseline and treated)

## What it does
Two independent binary classifiers per FR-3.1/3.2:
- **baseline** — P(recover | case, no intervention): trained on the synthetic
  control arm's realized outcomes.
- **treated** — P(recover | case, intervention, channel): trained on the synthetic
  treatment arm's realized outcomes, with the (randomly-assigned) channel used for
  that case as an explicit feature — FR-3.2's own definition includes channel as a
  conditioning variable, and it is one here, not folded into an average.

Outcomes are bootstrapped from the generator's ground-truth response curves
(`ml/outcomes.py`) — a case's cohort and its 0/1 recovery outcome are both
*realized* stochastically from `p_self_heal`/`p_recover_by_channel`, then that
realized outcome (never the underlying probability) is what each model trains on.

## Data
11988 control-arm and
12012 treatment-arm cases
(seed 20260302), each split 70/15/15 (stratified on the outcome).
Base recovery rate: 0.352 (control) vs 0.516 (treated) —
the treated arm's higher rate is exactly the aggregate uplift signal Phase 03's
uplift model is trying to attribute per case, not just on average.

## Metrics (held-out test set)
| Arm | AUC-ROC | PR-AUC | Gate |
|---|---|---|---|
| baseline | 0.7069 | 0.5633 | PASS (>= 0.7) |
| treated | 0.7052 | 0.6733 | PASS (>= 0.7) |

ROC curves: `ml/artifacts/propensity_baseline/roc_curve.png`,
`ml/artifacts/propensity_treated/roc_curve.png`.

## Known failure modes
- **Bootstrapped, not observed, outcomes.** Every label here comes from realizing
  the synthetic generator's own probabilities — this validates that the modeling
  *pipeline* can recover a known signal, not that it will perform this well on
  real historical outcomes, which do not exist yet for this system.
- **Channel choice in the treatment arm is uniform-random**, not the constrained
  bandit FR-9.2 specifies (that lands in Phase 06). `channel` is a real feature
  here, but its *distribution in the training data* reflects "pick any channel with
  equal probability," not what a live bandit would actually select — the model
  will need retraining once real channel-selection data exists, or it will have
  learned a channel-effectiveness pattern from an unrealistic assignment policy.
- **Same cold-start limitation as the classifier**: no repeat-customer history.
- **What would fix it:** real observed outcomes (as soon as Phase 06+10 exist to
  produce them) replacing the bootstrap, trained on the bandit's actual channel
  assignments rather than a uniform-random stand-in.
