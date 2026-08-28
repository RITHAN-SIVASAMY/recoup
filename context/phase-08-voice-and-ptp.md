# Phase 08 · Hinglish voice and promise-to-pay

**Day 6, first half · Hard 4-hour cap. The thirty seconds nobody else has.**

## Mission
A bounded Hinglish voice recovery flow that captures a structured promise-to-pay, suspends escalation until the promised date, and degrades safely when the conversation leaves the graph.

## Why judges care
Voice is named explicitly in the track brief and is materially harder than text, so most teams will skip it. Promise-to-pay memory is cheap to build, almost nobody includes it, and "the system went quiet because the customer promised Friday" lands instantly with anyone who has done collections.

## Read first
`docs/01-FRD.md` FR-10, FR-11 · `docs/06-COMPLIANCE-MATRIX.md` §3.5 (CON-02, CON-03)

## Build
- [ ] `voice/graph.py` — finite dialogue graph with explicit nodes and exits:
  `identify → disclose (mandatory, unskippable) → purpose → offer_resolution → {capture_ptp | objection | opt_out | human_transfer} → confirm → close`
- [ ] `voice/tts.py` — edge-tts with `hi-IN` / `en-IN` neural voices; natural code-mixed Hinglish phrasing per node
- [ ] `voice/asr.py` — faster-whisper locally; per-utterance confidence
- [ ] `voice/guards.py` — low ASR confidence, silence, hostility, distress/dispute/legal keywords → apologize, offer link or callback, end call, raise a human exception. **Never improvise**
- [ ] `voice/runtime.py` — orchestrates the turn loop; writes every turn as a case event; stores transcript, audio artifact and node path, hash-chained
- [ ] `llm/ptp.py` — Claude extraction into a strict schema `{amount, date, condition, confidence}`; below the confidence threshold → human verification, never an assumed promise
- [ ] PTP suspends escalation until `promised_date + grace`; the case shows `awaiting_promise`, never silently idle
- [ ] Follow-through: `kept` / `partial` / `broken` → trust score → FR-8 aggressiveness
- [ ] `tests/llm_eval/ptp_golden.jsonl` — 60+ Hinglish/English utterances; report precision, recall and **false-positive rate separately** (the dangerous class)
- [ ] Voice is cost-tier gated: the EV engine must clear it explicitly

## Definition of done
A recorded call in which a promise is captured, escalation visibly goes quiet until the promised date, and an out-of-graph utterance degrades gracefully rather than improvising. Disclosure is provably unskippable.

## Demo hook
15 seconds of call audio + the transcript with the node path highlighted + the timeline showing suppressed escalation.

## Guardrails
No open-ended negotiation. No commitment the system cannot honour. Disclosure and opt-out are mandatory nodes with tests. A low-confidence PTP is never treated as a promise.

## Cut line
If live telephony is fragile, render the call **offline as an audio artifact** against the same graph. The graph and the captured promise are the substance; live telephony is garnish.

## Prompt seed
> Read `context/phase-08-voice-and-ptp.md`. Implement the bounded dialogue graph, Hinglish TTS/ASR, the safety guards and PTP extraction with a confidence threshold. Add a test proving the disclosure node cannot be skipped and that an out-of-graph utterance always exits safely.

## Commit
`feat(voice): bounded Hinglish dialogue graph with promise-to-pay capture` · `Phase: 08-voice-and-ptp` · tag `phase-08`
