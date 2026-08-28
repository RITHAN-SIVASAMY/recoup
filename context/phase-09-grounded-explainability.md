# Phase 09 · Grounded explainability

**Day 6, second half · The chat layer that refuses to lie.**

## Mission
Natural-language answers over the audit log that cite specific event IDs and refuse when the log does not contain the answer — enforced by a CI benchmark.

## Why judges care
Everyone will bolt an LLM chat onto a dashboard. That is not a differentiator. A chat layer that is provably grounded, cites primary records, and refuses to speculate is the only version that survives a compliance review — and the refusal behaviour is the part that is genuinely hard.

## Read first
`docs/01-FRD.md` FR-14 · `docs/adr/0005-no-vector-db.md`

## Build
- [ ] `audit/retrieval.py` — Postgres full-text search over event payloads combined with structured filters (case, actor, event type, time range). Deterministic and explainable — the filter used is shown with the answer
- [ ] `audit/qa.py` — compose an answer **only** from retrieved events; every claim carries `[event:01J...]` citations rendered as links to the case timeline
- [ ] Hard refusal contract: if retrieval returns nothing sufficient, the answer states that the log does not contain it and **names what would need to be logged** to answer it
- [ ] PII redaction before every call; a test asserts no phone/email/name pattern can reach an outbound prompt
- [ ] Latency budget with a deterministic fallback (structured event summary rendered without the model)
- [ ] `tests/llm_eval/grounded_qa.jsonl` — 40 questions: 20 answerable, 20 deliberately unanswerable ("was the customer happy?", "what is their credit score?", "why did the CEO approve this?")
- [ ] CI job fails on any fabricated citation, any citation to a non-existent event ID, or a refusal rate below 95% on the unanswerable set
- [ ] Prompt files versioned in `llm/prompts/` and hashed into the answer record, so an old answer explains with the prompt that produced it

## Definition of done
Benchmark green in CI. Live demo of one cited answer and one explicit refusal.

## Demo hook
Type *"Why did we contact this account three times?"* → cited answer. Then *"Was this customer happy about the call?"* → refusal naming the gap.

## Guardrails
No answer without citations. No citation to an event that does not exist (validated programmatically before the answer is returned). Speculation is a defect, not a fallback.

## Cut line
Reduce the benchmark to 20 questions before ever dropping the refusal contract.

## Prompt seed
> Read `context/phase-09-grounded-explainability.md`. Implement grounded retrieval and Q&A over the event log with mandatory citations and an explicit refusal contract. Build the 40-question CI benchmark and make a fabricated citation fail the build. Validate every citation against real event IDs before returning an answer.

## Commit
`feat(audit): grounded Q&A with citations and enforced refusal` · `Phase: 09-grounded-explainability` · tag `phase-09`
