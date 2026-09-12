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

- [ ] The non-sensitive suite contains the approved 60-case Gate A composition and covers single
  and multiple Tasks, lifecycle intents, time ambiguity, corrections, short replies, greetings,
  emotional statements, irrelevant conversation, ownership, and prohibited mutations.
- [ ] Every case defines expected and prohibited Tools, clarification requirements, acceptable
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
