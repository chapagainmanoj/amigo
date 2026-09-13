# Model Evaluation

Amigo's Gate A model evaluation is a versioned, non-sensitive release check for the English Core
Loop. The authoritative behavior and threshold decisions are recorded in
[`09-model-evaluation-contract.md`](../.scratch/amigo-complete-product/decisions/09-model-evaluation-contract.md).

## Suite

[`evals/gate_a/v1/cases.json`](../evals/gate_a/v1/cases.json) contains 60 authored cases:

- 20 Task-creation cases
- 20 lifecycle cases
- 10 non-mutating conversation cases
- 10 hard-invariant and safety cases

Each turn declares expected and prohibited Tools, whether clarification is required, acceptable
response properties, expected resulting state, and independently scored metrics. Exact prose is
not scored unless a disclosure or prohibited claim requires it. The fixed evaluation clock and
timezone are part of the suite.

## Commands

Validate the fixture schema, composition, and thresholds without contacting Gemini:

```bash
python scripts/run_gate_a_eval.py --validate-only
```

Run one development case. This is diagnostic evidence, not a declared release run:

```bash
python scripts/run_gate_a_eval.py --case ga-task-01 --output /tmp/gate-a-case.json
```

If no archived passing run exists yet, establish the one-time baseline. This complete,
cost-bearing run is not release-candidate evidence:

```bash
python scripts/run_gate_a_eval.py \
  --establish-baseline \
  --output evidence/gate-a/last-passing.json
```

Then run the complete declared Gate A candidate against that baseline:

```bash
python scripts/run_gate_a_eval.py \
  --baseline evidence/gate-a/last-passing.json \
  --output evidence/gate-a/latest.json
```

The second command writes `evidence/gate-a/latest.comparison.json`. A human reviewer completes its
`human_review` object after inspecting tone, every score delta, and every new failure pattern. Do
not edit either run artifact.

A declared run executes all 60 cases three times. It requires the configured release model and a
billing-enabled `GOOGLE_API_KEY` with enough quota for at least 180 executions and their Tool-call
round trips. The default 13-second provider interval respects a five-request-per-minute limit;
adjust it only to match the approved provider quota.

## Evidence policy

The runner records the commit and dirty diff hash, exact model identifier, prompt and Tool-schema
hashes, model settings, Turn Context and time-behavior hashes, suite and validator versions,
each turn's pre-turn state hash, trace, response, resulting state, and scorer output, category
scores, latency, token usage, estimated list-price cost, date, environment, fixed clock/timezone,
model settings, pricing snapshot, and derived run totals.

Run all three repetitions as one predeclared run. Do not rerun an unchanged failure to obtain a
lucky pass. A provider quota response aborts the declared run as a documented provider incident;
start a replacement only after quota is restored. Never point the evaluator at production or use
real participant content: its channel is intentionally no-network and its state is isolated.

Every relevant pull request runs schema validation and deterministic scorer tests. Run the full
suite for each release candidate and whenever the model, prompt, Tool schema/description, Turn
Context, lifecycle/time behavior, safety rules, suite, or validator changes. Compare the resulting
artifact with the last passing baseline; a hard-invariant failure or any independently scored
category below its approved threshold blocks the gate.

The baseline is the archived full JSON from the most recent passing declared run, not a copied
score table. A release candidate must be a distinct run declared after that baseline completed.
The comparison binds the exact finalized baseline and candidate artifacts by SHA-256 and records
both run IDs, revisions, completion times, every per-metric baseline/candidate score and delta,
and complete baseline/candidate, new, and resolved failure-pattern sets. A failure pattern is one
authored case plus its failed metric combination, with affected repetitions attached. The
comparison is a separate file so its review fields do not create a circular candidate hash.

The generated comparison starts in `pending`. Passage requires a canonical reviewer identity,
UTC review time after candidate completion and inside the release evidence interval, nonempty
notes, explicit confirmation that the input was the last passing baseline, explicit tone review,
and an exact list of every derived new pattern ID. A future review time is invalid, and the
founder decision must be strictly later than the comparison review and every other evidence
timestamp. Human review records judgment; it cannot turn a hard-invariant or below-threshold
result into a pass.

That rule is enforced rather than remembered. `src/evaluation/gate_a.py` holds the single list of
invalidating inputs, and the checker recomputes every fingerprint from the tree:

```bash
python scripts/check_gate_a_evidence.py \
  --revision "$(git rev-parse HEAD)" \
  --evidence evidence/gate-a/latest.json \
  --baseline evidence/gate-a/last-passing.json \
  --comparison evidence/gate-a/latest.comparison.json
```

It is fail-closed, and it derives the verdict rather than reading it: every turn is rescored from
its authored expectation plus the retained pre-turn state hash, trace, response, and resulting
state. The recorded scorer output must exactly match that recomputation, and execution metrics
and category summaries are derived only from the recomputed scores. A hand-written turn score,
execution `metric_results`, category, or `passed` flag therefore proves nothing. Every execution
must name the exact authored case category and metric set and retain every authored turn's
message, pre-turn state hash, trace, response, resulting state, latency, usage, and complete scorer
output. Trace entries may name only Tools in the recorded/current Gate A schema; each call retains
its provider call ID and must have one later, nonempty result with the same ID and Tool name.
Resulting-state snapshots use one shared runner/checker schema. The checker validates every Task,
Reminder, and alias projection, recomputes the state SHA-256, and requires each later turn's
pre-turn hash to equal the prior retained result. Execution usage and list-price cost and the final
token/cost totals are also recomputed from turn evidence. A run is
refused when it is missing, unreadable, aborted on a provider incident, `--case`-scoped, short of
180 executions, missing repetition 1, 2, or 3 for any case, carrying an execution that did not
complete, scored below an approved threshold, executed from a dirty tree, executed
against another revision or another model, or when its recorded prompt, Tool schema, Turn
Context, time-behavior, migration, or suite fingerprints no longer match the working tree — the
failure names the input that changed. It also refuses a missing, malformed, non-passing,
self-selected, or later baseline; mismatched derived score/failure comparisons; and a missing,
pending, stale, or incomplete human review. The invalidating-input list is checked against the
import closure of the modules a run exercises, so a newly imported module cannot escape it. It is
not a pull-request gate, because a declared run costs 180 provider executions; it gates the
release, and
`scripts/validate_preflight_evidence.py` calls it on the `model_evaluation` artifact so a stale
run cannot be attached to a new release by typing a revision into the manifest.

## Current status

The 60-case contract and deterministic validation are implemented. No complete passing baseline
or release-candidate run is recorded: the development Gemini key reached its free-tier daily
request quota during probes. Because this is the first gated release, the authorized
higher-quota or billing-enabled resource must first produce the baseline and then a distinct
candidate run and reviewed comparison. Gate A remains open until all three artifacts exist and
pass the release-evidence checker.
