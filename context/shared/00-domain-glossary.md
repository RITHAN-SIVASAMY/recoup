# Shared context · Domain glossary

Use these words exactly. Consistent naming across code, docs, UI and commits is what makes the audit trail readable.

| Term | Meaning | In code |
|---|---|---|
| **Case** | One revenue-at-risk event, normalized. The unit of work | `domain.Case` |
| **CaseEvent** | An immutable fact about a case. The source of truth | `domain.CaseEvent` |
| **Source type** | `payment_failure` / `checkout_abandonment` / `mandate_failure` / `receivable_overdue` | `domain.SourceType` |
| **Root cause** | The diagnosed reason from the decline taxonomy | `case.root_cause` |
| **Propensity** | P(recover) under a given condition | `p_recover_baseline`, `p_recover_treated` |
| **Uplift (τ)** | `p_treated − p_baseline`. The only quantity worth optimizing | `case.uplift` |
| **Uplift segment** | `persuadable` / `sure_thing` / `lost_cause` / `sleeping_dog` | `case.uplift_segment` |
| **EV** | `uplift × amount × margin − channel_cost − goodwill_cost` | `economics.expected_value()` |
| **EV floor** | Minimum EV below which no action is proposed | `merchant.ev_floor_inr` |
| **Ladder** | Ordered permitted interventions for a root cause | `policies/ladders.yaml` |
| **Verdict** | `ALLOW` / `DENY` / `REQUIRE_APPROVAL` + rule ID + policy version | `policy.Verdict` |
| **Staged action** | Approved action held in a cancellable state before execution | `execution.StagedAction` |
| **Idempotency key** | `sha256(case_id ‖ action_type ‖ ladder_step ‖ policy_version)` | `execution.idempotency_key()` |
| **Cohort** | `treatment` or `control`, assigned at creation, immutable | `case.cohort` |
| **Adaptive holdout** | Control share that decays as evidence accumulates | `measurement.HoldoutController` |
| **CUPED** | Variance reduction with a pre-period covariate | `measurement.cuped()` |
| **PTP** | Promise-to-Pay: `{amount, date, condition, confidence}` | `domain.PromiseToPay` |
| **Trust score** | Promise-keeping reliability, modulates aggressiveness | `customer.trust_score` |
| **Degraded mode** | Running without the LLM, on deterministic paths only | `case.degraded_mode` |
| **Resolution state** | `recovered` / `pending` / `awaiting_promise` / `stopped_by_policy` / `abandoned_uneconomic` / `exception` / `control_untouched` | `domain.ResolutionState` |

**Never** use these loosely: "recovered" always means the money actually arrived; "incremental" always means measured against control; "compliant" always means a named rule with a test behind it.
