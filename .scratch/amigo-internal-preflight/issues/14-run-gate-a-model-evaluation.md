# Run the Gate A Model Evaluation

Status: open
Label: `ready-for-human`
Severity: `severity:high`
Type: AFK
Owner: Codex

## What to build

Create and run the versioned 60-case Internal Preflight model evaluation against the configured
release model, prompt, Tools, Turn Context, and time behavior. Score expected and prohibited Tools,
clarification, resulting state, factual behavior, and response properties rather than exact prose.

## Acceptance criteria

- [x] The non-sensitive suite contains the approved 60-case Gate A composition and covers single
  and multiple Tasks, lifecycle intents, time ambiguity, corrections, short replies, greetings,
  emotional statements, irrelevant conversation, ownership, and prohibited mutations.
- [x] Every case defines expected and prohibited Tools, clarification requirements, acceptable
  response properties, and expected resulting state.
- [ ] One declared evaluation run executes every case three times against exact recorded model,
  prompt, Tool schema, Turn Context, time behavior, and release revision inputs.
- [ ] Hard invariants, safety boundary, English output, and mutation-risk ambiguity pass 100%; each
  independently scored category meets its approved threshold.
- [ ] The run records traces, scores, latency, tokens, cost, date, environment, and release revision
  without retrying an unchanged failed candidate for a lucky pass.
- [ ] A deterministic subset runs on relevant pull requests and the complete Gate A suite runs when
  any invalidating model input changes.

## Blocked by

- [Resolve a Task and Reminder Consistently](06-resolve-task-and-reminder-consistently.md)
- [Apply Later Consistently Across Both Surfaces](07-apply-later-across-surfaces.md)
- [Clarify and Confirm Reminder Time](08-clarify-and-confirm-reminder-time.md)

## Delivery notes

- Affected areas: versioned evaluation fixtures, runner, model adapter, Tool assertions, CI or
  pre-deploy job, evidence output, and contributor documentation.
- Rollout: run locally or in controlled staging before making it a release-candidate gate.
- Rollback: remove a faulty runner from gating while retaining its evidence; do not waive a failed
  hard invariant.

## Comments

### 2026-08-31 — Claimed

Implementation started after the declared dependencies closed. The work uses the approved
60-case composition and three-repetition contract without introducing production or participant
data into the evaluator.

### 2026-09-01 — Contract implemented; declared run blocked by provider quota

The versioned suite now contains the exact 20 Task-creation, 20 lifecycle, 10 non-mutating, and
10 hard-invariant cases. Every turn declares Tool ranges, prohibited Tools, clarification,
response properties, resulting state, and metrics. The isolated runner records the exact release
inputs, traces, state, latency, tokens, list-price cost, environment, and independently scored
thresholds; provider quota errors abort rather than retrying an unchanged candidate.

CI validates the suite and deterministic scorer on every pull request. Local verification passes
with 213 backend tests, Ruff, scheduler smoke, dashboard lint/build, and the 60-case/3-repetition
schema check. Development probes exposed and led to fixes for combined Task/Reminder confirmation,
canonical Later, rescheduling, and planning-day moves.

The complete 180-execution declared run is not yet available. The configured Gemini key is on the
free tier and exhausted its 20-request daily quota during probes, which cannot support this run.
Finishing the evidence requires an authorized billing-enabled or higher-quota key. The planning-day
case also requires human approval of proposed migration 012 before its implementation can become
the release candidate. No acceptance criterion is marked complete until those blockers are
resolved and the resulting evidence is independently reviewed.

### 2026-09-11 — Migration 012 approved and added; planning-day blocker cleared

The project owner approved migration 012. `migrations/012_canonical_planning_day_move.sql` and
`tests/sql/move_task_planning_day_command.sql` are checked in, appended to the CI psql chain in
numeric order, and documented in the README migration list. The proposal was reconstructed from
current code (the earlier `/tmp` bytes were lost), independently reviewed before approval, and
independently reviewed again after adoption; both reviews passed. See
`.scratch/amigo-internal-preflight/reviews/012-canonical-planning-day-move.md`.

This clears the schema half of the planning-day blocker: the Supabase-backed
`move_task_planning_day_command` path now exists. A separate injected-clock defect found on the
same day is also fixed — `Clock.now_in_tz` and `Clock.local_time_to_utc` read the wall clock
instead of deriving from `utc_now()`, so `today_in_tz()` ignored the injected clock and the
planning-day guard compared against the real server date.

The declared 180-execution Gate A run remains blocked on an authorized billing-enabled or
higher-quota release-model credential. No acceptance criterion is marked complete.

### 2026-09-13 — Criteria 1 and 2 closed and made enforceable; criterion 6 enforced, run still missing

Criteria 1 and 2 were true in the suite but nothing held them true. `CATEGORY_COUNTS` proved only
the 20/20/10/10 composition, so an edit could have deleted every greeting, emotional-statement,
or ownership case and still validated; `expected_tools` and `prohibited_tools` both defaulted to
empty, so a turn that declared neither passed.

`GateASuite.validate_contract` now requires every behaviour family criterion 1 names —
single/multiple Tasks, lifecycle intents, time ambiguity, corrections, short replies, greetings,
emotional statements, irrelevant conversation, ownership, and prohibited mutations — to be
covered by at least one tagged case, and `EvalTurn.prohibited_tools` is a required non-empty
list. All 60 approved cases and all 64 turns satisfy the tightened contract unchanged. Both new
rejection tests were confirmed to fail against the previous contract, so neither passes
vacuously. Marking these two criteria complete.

Criterion 6's first half was already met: every pull request runs the schema validation and the
deterministic scorer tests. Its second half — the complete suite runs when any invalidating model
input changes — was recorded but never enforced. `_release_inputs` wrote fingerprints into the
evidence and nothing ever compared them, and the release manifest validated the Gate A artifact
only by path and SHA-256, so a stale run could be attached to a new release by typing the new
revision into `model_evaluation.revision`.

The invalidating-input list now lives once in `src/evaluation/gate_a.py`, and
`scripts/check_gate_a_evidence.py` recomputes every fingerprint from the working tree. It refuses
a run that is missing, unreadable, aborted on a provider incident, `--case`-scoped, short of 180
executions, missing a repetition, failed, executed from a dirty tree, executed against another
revision, scored against a lowered threshold, or scored on zero observations — and it names the
input that changed. `scripts/validate_preflight_evidence.py` calls it on the `model_evaluation`
artifact, so the release manifest can no longer accept an opaque or stale Gate A artifact. The
30 checker tests and 4 manifest tests were each confirmed to fail with the check removed.

The checker is deliberately not a pull-request gate: a declared run costs 180 provider
executions, so gating every pull request on one is not affordable, and CI would be permanently
red while the run is missing. It gates the release instead.

Criterion 6 stays unchecked. Enforcement now exists, but the thing it enforces — a complete
declared run — has never happened, and the criterion is about the run.

Criteria 3, 4, and 5 remain blocked on an authorized billing-enabled or higher-quota release-model
credential. That is an external blocker; no amount of repository work can close them.

Local verification: 299 backend tests pass, `ruff check src tests scripts` passes.

### 2026-09-13 — Independent review returned CHANGES REQUIRED; seven defects fixed

The review found the checker itself passed vacuously in four distinct ways, which is the same
failure mode as the Activation lock-order guard earlier in this session. Recording them plainly:

1. `scores` was read, never derived. A run in which **all 180 executions failed** was accepted as
   passing, because the checker believed the recorded `passed` flags. The summary is now
   recomputed from the executions with `summarize_scores` and compared; a hand-written summary is
   refused as `evidence.scores does not match the recorded executions`.
2. `score` was never compared with `threshold`, and `passed_observations` was never reconciled
   with `observations`. Every metric could record `score: 0.0` with `passed: true`. Now derived.
3. Execution status was a denylist of the single string `"error"`, so `"timeout"`, an absent
   status, and executions stripped to `case_id`/`repetition` all passed. It is now an allowlist
   requiring `status == "completed"` and `passed is True`. The fixture also disagreed with the
   runner — it wrote `"ok"`, a value `run_gate_a_eval.py` never emits — so the drift guard now
   checks the status string itself.
4. Repetitions were counted, not identified. Three records of repetition 1 satisfied "every case
   three times". The check now requires the exact set `{1, 2, 3}` per case.
5. Criterion 2 was **not** enforced and its tick was an overclaim. Only `prohibited_tools` had
   been tightened; every field of `ResponseProperties` and `ExpectedState` defaults to "do not
   care", so a turn could declare one prohibited Tool and assert nothing — and a task-creation
   turn where the model created nothing then scored `tool_and_state` and `task_extraction` as
   passes. `EvalTurn` now requires a turn to name its expected Tools or assert the state is
   unchanged, and to declare a non-default expected state. All 64 approved turns satisfy this
   unchanged, and a test demonstrates the free pass that motivated it.
6. The invalidating-input list was incomplete, and incompleteness fails **open**. `file_set_hash`
   hashes the paths it is handed, so listing `src/memory/store.py` did not cover the validators it
   delegates to: `src/memory/later.py`, `src/memory/tasks.py`, `src/memory/reminders.py`,
   `src/scheduler/reminders.py`, `src/commands/base.py`, and `src/config.py` — the model
   identifier itself — could all change without invalidating a run. The list is now the full
   `src` import closure of the modules a run exercises, and a test recomputes that closure and
   requires it to equal the list, so a new import cannot escape silently.
7. `tool_schema_sha256` was recorded by the runner but never recompared, while README and
   `docs/model-evaluation.md` claimed every fingerprint was checked. The Tool-schema builder moved
   into `src/evaluation/gate_a.py` and is now recomputed; the prose is corrected rather than
   softened. A binary artifact named `.json` also raised an uncaught `UnicodeDecodeError` out of
   `validate_manifest` instead of failing it.

Criterion 2 stays ticked only because the enforcement it names now exists. Every fix was
mutation-checked: removing the score recomputation, the status allowlist, the repetition-identity
check, or the turn-assertion validator each fails specific tests.

Local verification after the fixes: 323 backend tests pass, `ruff check src tests scripts` passes,
`git diff --check` clean.

### 2026-09-13 — Provider identity bound to executions; fabricated Gate A metric removed

Independent review found that the runner recorded a configured alias as the model identity and
that `dependency_error_handling` was scored as a literal alias of factual consistency.

The model-identity finding is fixed. The runner records the provider-reported model name on every
execution plus the installed `pydantic-ai-slim`, `google-genai`, and `pydantic` versions. The
evidence checker derives the aggregate identity from all 180 execution records, rejects a missing
or mixed identity, and invalidates evidence when those dependency versions change. Ordinary
execution errors retain an empty identity without crashing evidence capture.

The previous `dependency_error_handling` score was fabricated: `ga-life-14` has a valid zero-result
Tool response, not a dependency failure, and the runner aliased the metric to factual consistency.
The authoritative case inventory assigns dependency and Tool-result error scenarios to Gate B,
while the 95% threshold applies when that category is present. The unsupported metric is therefore
removed from Gate A rather than credited without observations. No case count, authored behavior,
or Gate A composition changed; `ga-life-14` remains and is scored for its actual contract.

Graceful dependency-error handling still requires implementation and the approved Gate B cases
before Gate B. Gate A remains open for its complete declared release-model run and independent
evidence review.

Final adversarial review also found and closed two evidence-integrity gaps: the aggregate provider
identity is now derived from exactly one nonempty provider-reported name on every completed
execution, and malformed mixed-type evidence returns validation errors instead of crashing. Error
executions retain an empty identity without breaking capture. The corrected Gate A case-set SHA-256
is `9f7c9988262e1d42a1884d86393a6a6ae63a11633864b834bcef6bf6ce1ef3ff`.

Independent re-review passed. Current local verification: 400 backend tests, Ruff, Gate A
60-case/3-repetition contract validation, frontend lint/build, and `git diff --check` all pass.

### 2026-09-13 — Last-passing baseline comparison made fail-closed

A later specification review found that the checker enforced candidate currency and thresholds
but never implemented Decision 09's required comparison with the last passing baseline. The
release path now requires three distinct artifacts: the full candidate run, the archived full
last-passing run, and a comparison report bound to both finalized run artifacts by SHA-256. The
checker validates
the historical artifact as a complete passing declared run, rejects candidate self-comparison or
a baseline that did not complete before candidate declaration, and independently recomputes every
metric score/delta and every baseline, candidate, new, and resolved failure pattern. Patterns are
stable authored-case plus failed-metric combinations with affected repetitions retained.

The comparison starts pending. It cannot pass release validation until its human reviewer
confirms the selected artifact is the last passing baseline, explicitly reviews subjective tone,
enumerates every derived new failure-pattern ID exactly, records a UTC review time after candidate
completion and inside the release interval, and adds notes. A future review is rejected and the
founder decision must follow the comparison review. Human review cannot override the existing
deterministic threshold and hard-invariant checks. The release manifest now requires separately
hashed candidate, baseline, and comparison artifacts and binds the comparison reviewer to the
model-evaluation evidence reviewer.

No real provider result is claimed. There is no archived complete passing run today, so the first
quota-capable session must use `--establish-baseline` for one full 180-execution run; a second,
distinct 180-execution candidate and its reviewed comparison are then required for this release.
Criteria 3–6 remain unchecked until those real artifacts exist and are independently reviewed.

A first independent review of this slice returned changes required: execution-level category and
metric declarations were still trusted, per-turn traces/scores were not required, the comparison
did not bind the candidate bytes, comparison review time was absent from release ordering, and a
JSON-list repetition could crash set insertion. The checker now binds each execution to its exact
authored category, metric set, and complete ordered turn evidence; derives execution metrics from
the per-turn scores; and rejects the demonstrated 179-empty/one-all-metrics forgery. The finalized
candidate digest is recomputed in both CLI and manifest paths, so changing only a trace after
approval invalidates the comparison. Repetition is validated as a non-boolean integer in 1–3
before set insertion, and CLI JSON reads catch decoding and I/O failures.

Local verification after these corrections: all 425 backend tests pass, the 98 focused
evidence/currency tests pass, Gate A validates 60 cases at three repetitions, Ruff is clean, and
`git diff --check` passes. Independent re-review is pending.

The second independent re-review found one remaining trust boundary: the checker validated the
shape of each retained turn score but still derived execution metrics from those stored booleans.
It now invokes the production `score_turn` function again for every authored turn using the exact
retained pre-turn state hash, trace, response, and resulting state. The recorded score must match
that recomputation field for field, while execution metrics and category summaries are derived only
from the recomputed values. Malformed nested trace/state evidence is rejected before rescoring.
An adversarial regression leaves every stored boolean green while adding prohibited
`apply_later` behavior and a non-English response; direct checker, CLI, and release-manifest paths
all reject it.

Comparison failure-pattern construction now treats non-list execution collections as invalid
input rather than raising, including the valid-JSON `executions: 5` candidate/baseline cases. No
provider run is claimed and criteria 3–6 remain open.

Local verification after the second corrections: all 436 backend tests pass, the 109 focused
evidence/currency tests pass, Gate A validates 60 cases at three repetitions, Ruff is clean, and
`git diff --check` passes. Independent re-review is pending.

The third independent pass found that trace and state evidence still admitted internally
impossible artifacts and that several Decision 09 metadata fields were merely recorded, not
validated. The trace contract now retains pydantic-ai Tool call IDs, permits only nonempty names
from the actual Gate A Tool schema, and requires every ordered call to have a later nonempty result
with the same ID and Tool name. Non-string and unhashable JSON `kind` values, unknown Tools,
orphan results, unmatched calls, and malformed result content return blockers without exceptions.
The shared passing fixture now contains the runner-faithful 117 calls and 117 matching results.

Runner and checker now share one canonical state snapshot/hash implementation. It enforces exact
nested Task, Reminder, and alias projections, alias-to-Task consistency, full-state SHA-256
recomputation, and multi-turn hash chaining. Contradictory aliases, a changed field behind a stale
hash, a fabricated hash, and a disconnected next-turn hash all fail adversarial regressions.

The checker also validates the controlled environment, pricing snapshot, retry policy, request
interval, provider/model settings, Tool schema, case-set version, fixed clock/timezone, clean diff
hash, aggregate execution latency/usage/cost, and recomputed run token/cost totals. This hardening
does not claim a provider run; criteria 3–6 remain open.

Local verification after the third corrections: all 466 backend tests pass, the 138 focused
evidence/currency tests pass, Gate A validates 60 cases at three repetitions, Ruff is clean, and
`git diff --check` passes. Independent re-review is pending.
