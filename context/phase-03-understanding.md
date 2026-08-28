# Phase 03 · Understanding — the ML layer

**Day 3 · full day · The phase that must survive a data-science question.**

## Mission
Calibrated root-cause classification, baseline and treated propensity, uplift estimation with segmentation, LTV/relationship scoring, SHAP attribution, model cards, and a CI metric gate.

## Why judges care
"Meaningful use of AI" and "honest performance metrics" are explicit. A calibrated classifier with a published confusion matrix and a written failure-modes section is a stronger signal than a bigger accuracy number with no error analysis. Uplift is the idea most teams will not have.

## Read first
`docs/01-FRD.md` FR-2, FR-3, FR-8 · `docs/05-EVALUATION-PROTOCOL.md` §4 · `docs/adr/0007-uplift-x-learner.md`

## Build
- [ ] `ml/train_classifier.py` — LightGBM multi-class over the decline taxonomy; stratified 70/15/15 split with **no customer leakage across splits**
- [ ] Isotonic/Platt calibration + reliability curve + Brier score. The EV engine consumes these as real probabilities, so uncalibrated output is a defect
- [ ] SHAP top-k per case, persisted on the case and written into the audit trail
- [ ] `ml/train_propensity.py` — baseline (control arm) and treated (treatment arm) models
- [ ] `understanding/uplift.py` — X-learner over the two base models; τ per (case, action); segmentation into `persuadable | sure_thing | lost_cause | sleeping_dog`
- [ ] Qini curve + uplift-at-k, plus agreement with the generator's ground-truth τ
- [ ] `understanding/relationship.py` — LTV, relationship risk, trust score inputs
- [ ] `understanding/priority.py` — `uplift × amount × urgency_decay × relationship_weight`
- [ ] Model cards in `ml/cards/*.md`, each with a **Known failure modes** section in plain English
- [ ] `model_versions` recorded on every scoring event
- [ ] CI job: retrain on the seeded data, fail the build if macro-F1 < 0.85, Brier > 0.12, or Qini ≤ 0

## Definition of done
Metrics met and published; confusion matrix and calibration plot committed as artifacts; failure modes written honestly; every score traceable to a model version.

## Demo hook
Case detail showing root cause with calibrated confidence, SHAP bars, uplift, and the segment label — and a `sure_thing` case the system deliberately leaves alone.

## Guardrails
No model output bypasses calibration. No ground-truth leakage. If a metric misses the bar, lower the bar in the document and say so — never tune the test.

## Cut line
If uplift training is unstable, ship the documented heuristic (treated propensity − self-heal prior), label it a heuristic in the UI and the model card, and explain the production path. Never present a heuristic as a model.

## Prompt seed
> Read `context/phase-03-understanding.md` and §4 of `docs/05-EVALUATION-PROTOCOL.md`. Train the classifier, propensity and uplift models. Report metrics honestly, including a written "Known failure modes" section per model card, and wire the CI metric gate.

## Commit
`feat(ml): calibrated root-cause classifier, propensity and uplift models` · `Phase: 03-understanding` · tag `phase-03`
