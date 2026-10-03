# Add Model Policy, Content-Free Turn Tracing, and Per-Mode Evaluation

Status: closed
Label: `done`
Severity: `severity:medium`
Type: AFK
Owner: unassigned
Phase: 2 of 5
Blocked by: [01-build-modular-mode-foundation.md](01-build-modular-mode-foundation.md)

## Problem Statement

After the foundation lands, every Mode is declared data, but three things any second Mode needs are
still missing.

- **Models.** A Mode can name one model and nothing else. When Gemini is unavailable, every Turn
  in every Mode returns the friendly failure reply, and nothing can declare a second evaluated
  model to use instead.
- **Visibility.** The only per-Turn record is one log line naming the Mode. The founder cannot see
  which model answered, how long it took, how many tokens it used, or what it cost. The pricing
  hypothesis (decision 12) needs variable cost at or below US$2.25 per active subscriber, and
  nothing measures it.
- **Evaluation.** Each Mode declares an evaluation suite, but the runner is hard-wired to Daily's
  Gate A suite. No continuous-integration job runs any Mode's deterministic cases, so a Mode could
  go live with no evaluation at all.

## Solution

- **Model policy.** Each Mode declares a model policy instead of a bare model name: a primary model,
  an optional ordered fallback, and model settings. The runtime keeps the existing single retry.
  It moves to the fallback model only when the provider is unavailable, and only when no Tool has
  run in the Turn, so a fallback can never repeat a side effect.
- **Turn Record.** Every Turn emits one content-free record: the Mode, the model that answered,
  whether a fallback was used, the names of the Tools that ran, the outcome, latency, token usage,
  and estimated cost. It goes to the structured logs and to an OpenTelemetry span with content
  capture off.
- **Per-Mode evaluation.** Every live Mode must declare an evaluation suite that exists. The runner
  evaluates any Mode by its identifier. Continuous integration runs every live Mode's
  deterministic subset on relevant pull requests.

Daily's instructions, Tools, and model stay unchanged. Daily declares no fallback until a fallback
model has its own passing Gate A run.

## User Stories

1. As a participant, I want Amigo to keep answering when the primary model provider is briefly unavailable, so that one provider outage doesn't make Amigo useless.
2. As a participant, I want a Task or Reminder never to be created twice because Amigo retried on another model, so that fallbacks can't duplicate my plans.
3. As a participant, I want the friendly failure reply when every declared model is unavailable, so that a failure never looks like a crash.
4. As a participant, I want none of my message text, Task titles, or Tool arguments to appear in traces or cost records, so that my content stays out of operational tooling.
5. As the founder, I want each Mode to declare its primary model, its fallback, and its model settings, so that Modes can use different models without code changes to the runtime.
6. As the founder, I want to see which Mode and which model handled each Turn, so that I can diagnose quality differences between Modes and models.
7. As the founder, I want token usage and estimated cost per Turn, per Mode, and per participant-day, so that I can check the US$2.25 variable-cost limit.
8. As the founder, I want the cost of a Turn on an unknown-price model reported as unknown rather than zero, so that cost is never understated.
9. As the founder, I want to know how often fallbacks happen, so that I can spot a failing provider.
10. As the founder, I want no Mode to go live without a declared, existing evaluation suite, so that every live Mode can be evaluated.
11. As the Gate A evaluator, I want to run the evaluation for any Mode by its identifier, so that adding Modes doesn't mean forking the runner.
12. As the Gate A evaluator, I want a Mode's fallback model to count as a model change under decision 09, so that an unevaluated model never answers participants.
13. As the Gate A evaluator, I want Daily's prompt hash, Tool-schema hash, and model unchanged by this work, so that no declared evaluation evidence is invalidated.
14. As a developer, I want every live Mode's deterministic evaluation subset to run on relevant pull requests, so that a regression is caught before merge.
15. As an operator, I want tracing to be a no-op unless a trace exporter is deliberately installed, so that deploying this changes no environment's behaviour.
16. As an operator, I want no runtime-configuration default change and no migration, so that this deploys without protected review.
17. As a security reviewer, I want fallback limited to provider-unavailability errors, so that a model that refuses or misbehaves is never "retried until it complies".

## Implementation Decisions

- **Model policy value.** A Mode's `model` becomes a model policy with:
  - a primary model reference, which can be "the configured default";
  - at most one fallback model reference;
  - optional model settings.
  Daily's policy is the configured default with no fallback and no settings, which keeps its Gate A
  inputs identical.
- **When the fallback runs.** The existing single provider retry is unchanged (CLAUDE.md rate-limit
  rule). The fallback model is tried exactly once, and only if all of these hold:
  - the primary failed with a provider-unavailability error (connection failure, timeout, server
    error, or rate limit after the retry);
  - no Tool call executed in this Turn;
  - the failure was not a validation, output, Tool, or content error.
  Otherwise the Turn fails with the friendly reply, as today. Nothing loops.
- **Fallback is a model change.** A live Mode may declare a fallback model only once that model has
  a passing Gate A run for that Mode. A test ties every declared fallback on a live Mode to an
  evidence-manifest entry. Whether the Gate A contract version is bumped is left to the implementer
  and reviewer. Cross-provider fallback that needs a new secret is out of scope, because it
  requires a `src/config.py` change.
- **Turn Record.**
  - **Fields:** a record-schema version, turn id, Mode id, requested model, answering model, a
    fallback-used flag, the names of the Tools that ran (names only), and the outcome (`ok`,
    `refused`, or `failed` with an error class). Also latency in ms, input and output tokens, and
    estimated cost in USD, or `null` when the price is unknown.
  - **Never included:** message text, instructions, Tool arguments, Tool results, participant name,
    chat id, or timezone. The participant is identified only by the existing pseudonymous user id.
  - **Destinations:** one structured log line per Turn, and an OpenTelemetry span through the model
    framework's instrumentation with content capture off. Spans go to the global tracer provider,
    which is a no-op unless an operator installs one. Setting up an exporter is out of scope.
- **Cost.** Estimated from token usage with the model framework's price data (`genai-prices`, which
  is already a transitive dependency). An unknown model or price gives `null`, never `0`.
- **Refusals.** A refused Turn emits a Turn Record with outcome `refused` and no model fields.
  Refusal still writes nothing to the store.
- **Evaluation suite required.** Registration fails if a live Mode declares no evaluation suite or
  names a path that doesn't exist. Daily keeps `evals/gate_a/v1/cases.json`.
- **Generic runner.** The evaluation runner takes a Mode id, resolves the Mode through the
  registry, evaluates its declared suite, and records the model policy in the run evidence. It
  keeps recording the observed model names and dependency versions.
- **CI subset.** Continuous integration runs each live Mode's deterministic subset (scripted model,
  no provider call) on pull requests that touch any path in that Mode's invalidating-input list.
  This shares an implementation with the CI criterion of
  [preflight issue 14](../../amigo-internal-preflight/issues/14-run-gate-a-model-evaluation.md).
  Build it once, and mark it done in both issues.
- **Boundaries unchanged.** No migration, no store method change, no `src/config.py` change, and
  the model framework stays behind the runtime (ADR 0002).

## Testing Decisions

- **Good tests** drive a Turn through the bot handlers with a scripted model and assert what can be
  observed: the reply, the persisted Messages, created Tasks and Reminders, and the emitted Turn
  Record. They never assert on runtime internals.
- **Fallback behaviour:**
  - a primary that raises provider-unavailable produces the fallback's reply and a record with the
    fallback flag set;
  - a primary that runs `create_task` and then fails produces no fallback and exactly one Task;
  - a validation or content error produces no fallback;
  - a fallback that also fails produces the friendly reply;
  - exactly one fallback request is ever made.
- **Content-free record.** Using a participant message, name, and Task title containing unique
  sentinel strings, assert that no sentinel appears in any emitted log record or exported span
  (in-memory span exporter). Assert the same for Tool arguments and results.
- **Cost.** A known model gives a positive cost. An unknown model gives `null`.
- **Registration.** A live Mode with no suite, or with a missing suite path, is rejected.
- **Unchanged Daily.** The Daily Tool-schema hash and the golden Daily instructions still pass
  unchanged.
- **Prior art:** `tests/test_modes.py` (the scripted `FunctionModel`, runtime override, and
  registration tests) and the Gate A currency and import-closure tests.
- **Verification before completion:** the full backend suite, Ruff, Gate A contract validation, the
  scheduler smoke check, and a clean `git diff --check`.

## Out of Scope

- Cross-provider fallback that needs a new secret or runtime-configuration setting.
- Installing or configuring a trace exporter, dashboards, or alerting.
- Persisting Turn Records in the database.
- Real entitlements and participant grants (moved to
  [03](03-switch-modes-with-confirmed-handoffs.md), which already carries a migration).
- Any new Mode, routing change, or Daily prompt change.
- Declaring a fallback for Daily before a fallback model has a passing Gate A run.

## Further Notes

- **Scope change from issue 01's phase plan.** Issue 01 put "real entitlements" in Phase 2. They
  are moved to issue 03: a participant grant needs durable storage, and issue 03 already carries a
  protected migration. Keeping them here would add a second migration and make this issue
  human-in-the-loop.
- The Turn Record's fields are the telemetry that the privacy decision (04) already permits:
  delivery, latency, model usage, and cost. Adding a field that carries participant content needs a
  privacy decision first.

## Comments

- 2026-10-03 — Implementation complete for review: model policy, provider-only fallback guarded by
  actual Tool dispatch, one content-free structured Turn Record, framework tracing with content
  disabled plus an operational-attribute allowlist/error-text redaction, token/pricing accounting,
  live-suite enforcement, hash-linked/rescored fallback evidence, Mode/model-aware evaluation, and
  all-live scripted CI subsets. Daily prompt bytes, Tool schemas/order, primary settings, and no
  fallback remain unchanged. No migrations, protected defaults, Store interfaces, or exporters.
  Full verification and independent review are recorded before closure.
- 2026-10-03 — Implementation verification: 553 backend tests passed; Ruff clean; Daily Gate A
  contract validated (60 cases × 3); every live Mode's scripted subset passed; scheduler smoke and
  CLI/callback imports passed; tracked and untracked whitespace validation clean. Independent
  review requested; issue remains open until acceptance.
- 2026-10-03 — Independent review requested four corrections. Implemented current fallback
  execution-source/SDK/behavior currency validation; an actual single primary availability retry
  (Agent's validation retry does not retry provider HTTP failures); observed-model fallback
  pricing; and observed-model pricing/null propagation in the generic runner and checker. Added
  regressions rejecting stale source/SDK/order, known-alias unknown-observed costs, and forged
  fixed pricing for a non-Daily Mode. Reverification and independent recheck pending below.

### 2026-10-03 — Independent re-review passed; issue closed

A separate reviewer returned PASS on standards and specification after verifying all four
corrections. Fallback authorization checks current execution sources, SDK versions, instructions,
Tool schema and presentation order, and context declarations. Primary provider-unavailability
failures receive at most two attempts before any Tool dispatch; fallback receives exactly one
attempt without validation retry. Both runtime and generic evaluation account for observed model
identities and preserve unknown costs as `null`.

Independent verification: 558 backend tests passed, including 184 focused Mode/currency tests;
Ruff, Daily Gate A 60-case/3-repetition validation, every live Mode's deterministic subset,
scheduler smoke, CLI/callback imports, and tracked/untracked whitespace checks passed. No guarded
configuration, singleton, smoke implementation, or migration files were changed.

This closes the model-policy, tracing, and per-Mode evaluation prerequisite. Daily remains the only
live production Mode. Explicit switching, grants, confirmed handoffs, and Coach behavior follow
in issues 03 and 04. No provider evaluation or trial evidence is claimed by this closure.
