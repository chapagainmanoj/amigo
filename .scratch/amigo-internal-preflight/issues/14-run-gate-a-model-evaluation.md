# Run the Gate A Model Evaluation

Status: open
Label: `ready-for-agent`
Severity: `severity:high`
Type: AFK
Owner: unassigned

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

