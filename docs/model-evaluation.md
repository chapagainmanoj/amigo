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

Run the complete declared Gate A evaluation:

```bash
python scripts/run_gate_a_eval.py --output evidence/gate-a/latest.json
```

A declared run executes all 60 cases three times. It requires the configured release model and a
billing-enabled `GOOGLE_API_KEY` with enough quota for at least 180 executions and their Tool-call
round trips. The default 13-second provider interval respects a five-request-per-minute limit;
adjust it only to match the approved provider quota.

## Evidence policy

The runner records the commit and dirty diff hash, exact model identifier, prompt and Tool-schema
hashes, model settings, Turn Context and time-behavior hashes, suite and validator versions,
per-turn traces and resulting state, category scores, latency, token usage, estimated list-price
cost, date, and environment.

Run all three repetitions as one predeclared run. Do not rerun an unchanged failure to obtain a
lucky pass. A provider quota response aborts the declared run as a documented provider incident;
start a replacement only after quota is restored. Never point the evaluator at production or use
real participant content: its channel is intentionally no-network and its state is isolated.

Every relevant pull request runs schema validation and deterministic scorer tests. Run the full
suite for each release candidate and whenever the model, prompt, Tool schema/description, Turn
Context, lifecycle/time behavior, safety rules, suite, or validator changes. Compare the resulting
artifact with the last passing baseline; a hard-invariant failure or any independently scored
category below its approved threshold blocks the gate.

## Current status

The 60-case contract and deterministic validation are implemented. A complete release run is not
yet recorded: the development Gemini key reached its free-tier daily request quota during probes.
Gate A therefore remains open until a single complete run succeeds with an authorized
higher-quota or billing-enabled key.
