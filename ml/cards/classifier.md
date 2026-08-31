# Model card — root-cause classifier

## What it does
Classifies `payment_failure` and `mandate_failure` cases into one of nine causes
(`bank_soft_decline, card_expired_or_invalid, insufficient_funds, issuer_risk_block, mandate_insufficient_balance, mandate_revoked, mandate_technical_failure, network_or_gateway_error, otp_timeout_or_auth_abandon`). `checkout_abandonment` and
`receivable_overdue` are read directly off `source_type`, not classified — see
`ml/train_classifier.py`'s module docstring for why folding those in would be
dishonest about what the model is actually doing.

## Data
12000 synthetic cases (seed 20260301), filtered to
payment/mandate failures, stratified 70/15/15 into 4904 train /
1051 calibration / 1052 test cases. Every synthetic
customer is unique, so a row-level and a customer-grouped split coincide here — see
the note in `ml/train_classifier.py::_split`.

## Metrics (held-out test set)
- **macro-F1: 0.8804** (gate: ≥ 0.85)
- **Brier score: 0.0187** (gate: ≤ 0.12, isotonic-calibrated one-vs-rest)
- Confusion matrix: `ml/artifacts/classifier/confusion_matrix.png`
- Reliability curve: `ml/artifacts/classifier/reliability_curve.png`

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| bank_soft_decline | 0.88 | 0.86 | 0.87 | 176 |
| card_expired_or_invalid | 1.00 | 1.00 | 1.00 | 101 |
| insufficient_funds | 0.95 | 0.98 | 0.97 | 201 |
| issuer_risk_block | 0.85 | 0.93 | 0.89 | 71 |
| mandate_insufficient_balance | 0.71 | 0.78 | 0.75 | 124 |
| mandate_revoked | 0.87 | 0.76 | 0.81 | 88 |
| mandate_technical_failure | 0.88 | 0.88 | 0.88 | 147 |
| network_or_gateway_error | 0.94 | 0.67 | 0.79 | 49 |
| otp_timeout_or_auth_abandon | 0.95 | 1.00 | 0.97 | 95 |

## Feature attribution (mean absolute SHAP, top 6)
| Feature | Mean \|SHAP\| |
|---|---|
| error_reason | 1.5891 |
| source_type | 1.4802 |
| consecutive_failures | 1.2588 |
| relative_amount | 0.4562 |
| amount_at_risk | 0.4506 |
| hour_of_day | 0.3232 |

## Known failure modes
- **Irreducible label noise, by construction.** The generator resamples ~8% of
  labels to a confusable alternate (e.g. a `bank_declined` code is sometimes truly
  an `issuer_risk_block`) to avoid a classifier that's just a lookup table wearing
  a model's clothes — see `CONFUSION_PROBABILITY` in `data/distributions.py`. That
  noise puts a real ceiling on achievable macro-F1 well below 1.0; the number above
  is not being compared against a clean-label upper bound.
- **`network_or_gateway_error` is the smallest class** by construction (~5% of
  payment failures) and is the class most likely to have the widest confidence
  interval on its per-class F1; treat that row as the least trustworthy in isolation.
- **No customer-history features.** FR-2.2 lists prior-attempt features and
  customer history as candidate inputs; this synthetic batch has no repeat
  customers, so every case is effectively `cold_start` (FR-2.7) and the model has
  never had the chance to learn from repeat behavior. That's a real, not cosmetic,
  gap versus the FRD's stated feature set.
- **Mandate signal is thin.** `consecutive_failures` and `status` are the only
  mandate-side features; a real e-mandate failure carries considerably more
  structured detail (issuer NPCI response codes) that this synthetic batch does
  not model.
- **What would fix it:** real (or richer synthetic) customer-history features,
  and a larger, independently-sourced confusion matrix for the decline-reason →
  root-cause mapping instead of the documented assumption in `data/distributions.py`.
