# Shared context · Guardrails and anti-patterns

## Hard stops — if you are about to do any of these, stop and ask

1. Call an LLM from a code path that decides whether an action is permitted, or that executes one.
2. Write to the `cases` table without appending a `CaseEvent`.
3. Put a business or regulatory rule in Python instead of `policies/*.yaml`.
4. Use `float` for money, or a naive `datetime`.
5. Send anything to a customer that did not pass through a `staged` state.
6. Add a third-party service or a heavy dependency without an ADR.
7. Report a metric without its uncertainty, or round a null result into a win.
8. Let a control-cohort case receive any action, for any reason.
9. Put a raw phone number, email, name or account number into an LLM prompt.
10. Catch an exception and continue without an event and an exception-queue entry.

## Failure handling contract

Every external interaction: explicit timeout → bounded retry with jitter → circuit breaker → on final failure, write an event and route to the exception queue. **Never** mutate case state before the call succeeds.

Every LLM interaction: PII-redact → call with latency budget → validate against the Pydantic schema → on invalid or timeout, retry once → on second failure, fall back to the deterministic path and set `degraded_mode`. Recovery must never block on model availability.

## The five questions to ask yourself before finishing a phase

1. If this action ran twice, what would happen? (It must be a no-op.)
2. If the process died halfway through, what would the state be? (Consistent, or in the exception queue.)
3. Can I reconstruct why this happened from the log alone? (If not, an event is missing.)
4. Which test would fail if someone deleted this guardrail? (If none, write it.)
5. Would this number survive being challenged on stage? (If not, report the uncertainty.)
