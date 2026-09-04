# How this repository was built

Recoup was written with [Claude Code](https://claude.com/claude-code) as the
primary implementer, under a written contract rather than ad-hoc prompting.
This file explains that workflow, because "an AI wrote it" is not a useful
statement on its own — *what constrained the AI* is the part that matters.

## The contract

[`CLAUDE.md`](CLAUDE.md) is loaded into every session automatically. It is not
a style guide; it is a set of refusals. The ten ground rules there exist
because each one is a mistake an unconstrained model will otherwise make:

| Rule | The failure it prevents |
|---|---|
| The LLM never executes | a model deciding to charge a customer |
| No unlogged side effects | state changes with no audit trail |
| Policy is data, not code paths | compliance rules scattered as `if` statements |
| Deterministic first | a demo that can't be reproduced |
| Exact money | `float` rounding on real rupees |
| Honest metrics only | a null result dressed up as a win |

Several of these are enforced by tests rather than trust — an architecture test
fails the build if anything outside `audit/` writes to the `cases` table, or if
an LLM call appears in a decision path.

## The loop

Each of the thirteen phases has a context file in [`context/`](context/) with
an objective, a definition of done, and a `make gate PHASE=NN` acceptance
check. The working agreement for a session is:

1. Read the phase's context file and `context/shared/*.md`.
2. Restate the objective and plan **before** writing code; wait for approval.
3. Build in vertical slices that keep `make demo` working.
4. Run the phase gate. A red gate means the phase is not done.
5. Commit with a `Phase:` trailer. Anything that cost more than fifteen
   minutes gets an entry in [`docs/09-INCIDENT-LOG.md`](docs/09-INCIDENT-LOG.md).

The specification in the `docs/` submodule is authoritative. Where instinct
conflicted with the spec, the spec won or an ADR was raised — the point of
writing the FRD first was to have something that could overrule the model
later.

## What went wrong

[`docs/09-INCIDENT-LOG.md`](docs/09-INCIDENT-LOG.md) is the honest record: 25
incidents, each with what broke, how long it cost, and how it was fixed. It
includes bugs the agent itself introduced and did not notice until something
forced the question — most seriously INC-025, where case IDs were minted from
wall-clock time inside a supposedly seeded pipeline, so every "reproducible"
demo run silently produced a different cohort split. Every test passed.
`mypy --strict` passed. The code *looked* deterministic. It took explicitly
diffing two from-empty-database runs to catch it.

That entry is in the log rather than quietly fixed because the interesting
claim of this repo is not "AI wrote a working system." It is that a written
contract, phase gates, and an adversarial verification step caught the class
of error that confident-looking generated code produces.

## Contributing

```bash
git clone --recurse-submodules https://github.com/RITHAN-SIVASAMY/recoup.git
cd recoup && make setup
make gate PHASE=11     # or whichever phase you're touching
```

Before opening a PR: `make gate` green, a `Phase:` trailer on the commit, and
— for anything in `policy/` — the invariant test written **before** the
implementation, per ground rule 7.
