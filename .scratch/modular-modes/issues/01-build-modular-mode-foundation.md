# Build the Modular Mode Foundation

Status: closed
Label: `done`
Severity: `severity:medium`
Type: AFK
Owner: unassigned

## Problem Statement

Amigo can only ever be one agent. Daily's instructions, Tools, Turn Context assembly, Session
history handling, and failure handling are fused into a single module-level agent object, and the
Telegram Turn calls that one agent directly. Adding any second Mode — Coach, Reflect, Recommender,
or a Mode not yet imagined — means copying Tools, re-implementing Turn Context assembly, re-stating
the safety rules by hand, and editing the Turn loop itself. Nothing stops a new Mode from receiving
Tools it must never use, or from silently omitting the non-clinical and Crisis Referral rules.

For the founder this means every new Mode is a risky refactor rather than an addition, and the
product cannot grow Modes, gate them per participant, or later accept external agents without
reworking the core. Business policy — which Modes are live, who may use them, whether routing is
automatic — is currently baked into structure instead of being something that can be changed.

## Solution

A Mode becomes a declared, registered definition rather than a hand-built agent. A single Mode
runtime owns everything every Mode shares: resolving which Mode handles a Turn, checking the
participant may use it, composing the Safety Core with the Mode's own instructions and Turn
Context, running the model with only that Mode's Tools, persisting Session Messages, and turning
failures into the existing friendly reply. Tools are grouped into reusable toolsets in the Tools
module, each calling the shared Commands directly, so any Mode can use any combination.

Daily is migrated onto this foundation with the same Tools, the same Tool schemas, and the same
instruction text. One behaviour does change, deliberately: the instructions now reach the model on
every Turn. Before this work they were silently dropped from every Turn after the first in a
Session (see Comments). Coach, Reflect, and Recommender are registered as
planned Modes that the runtime refuses to run. From then on, adding a Mode means writing its
instructions, choosing its toolsets, declaring its Turn Context providers, and registering it —
the Turn loop, Safety Core, history, and failure handling are never touched.

Policy is configuration: which Modes are live, which entitlement a Mode requires, and which routing
policy resolves a Turn are all declared values, so a later decision can change them without a
refactor.

## User Stories

1. As a participant, I want my Telegram messages to be handled exactly as they are today after this change, so that nothing I rely on breaks.
2. As a participant, I want Tasks I describe to be captured with the same wording and confirmation as before, so that my Inbox and planning day stay accurate.
3. As a participant, I want Reminders to be scheduled, rescheduled, cancelled, and deferred with Later exactly as before, so that I keep trusting their timing.
4. As a participant, I want the same friendly reply when Amigo cannot think, so that a failure never looks like a crash.
5. As a participant, I want every Mode I ever use to follow the same non-clinical, Crisis Referral, and untrusted-input rules, so that switching Modes never makes Amigo less safe.
6. As a participant, I want a Mode that is not yet available to be refused plainly rather than half-working, so that I am never misled about what Amigo can do.
7. As a participant, I want a Mode I am not entitled to use to be refused with a clear reason, so that I understand why it is unavailable.
8. As a participant, I want a Mode to be unable to touch my Tasks or Reminders unless that Mode is meant to, so that exploring a new Mode cannot change my plans by accident.
9. As a participant, I want my conversation history in a Session to be kept the same way regardless of Mode, so that context is not lost or duplicated.
10. As a participant, I want Daily to remain my default when I have not chosen anything else, so that Amigo behaves predictably.
11. As the founder, I want to add a new Mode by declaring it rather than editing the Turn loop, so that each new Mode is an addition and not a refactor.
12. As the founder, I want each Mode to declare the toolsets it may use, so that a Mode can only ever call the Tools it was given.
13. As the founder, I want Tools grouped into reusable toolsets, so that two Modes can share Task Tools without duplicating them.
14. As the founder, I want each Mode to declare its own Turn Context providers, so that Coach can see its Coaching Program without Daily's Task list being forced on it.
15. As the founder, I want Turn Context providers to be reusable public building blocks, so that no Mode reaches into private helpers to assemble its prompt.
16. As the founder, I want the Safety Core defined once and guaranteed in every live Mode, so that no Mode can ship without it.
17. As the founder, I want registration to fail loudly if a live Mode's instructions cannot render or it orders Tools it does not have, so that the mistake is caught before it reaches a participant.
18. As the founder, I want a Mode's live, planned, or disabled status to be a declared value, so that launching or pulling a Mode is a one-line change.
19. As the founder, I want the entitlement a Mode requires to be a declared value, so that making a Mode premium later is configuration rather than code.
20. As the founder, I want the routing policy to be a replaceable component, so that I can move from explicit selection to automatic routing later without rewriting the runtime.
21. As the founder, I want the model a Mode uses to be declared per Mode, so that different Modes can later use different models or fallbacks.
22. As the founder, I want each Mode definition to reference its own evaluation suite, so that every Mode can be tested on its own behaviour.
23. As the founder, I want duplicate Mode identifiers rejected at registration, so that two Modes can never silently shadow each other.
24. As the founder, I want an unknown Mode identifier to be refused rather than falling back silently, so that a typo never runs the wrong Mode.
25. As the founder, I want the model framework to stay inside the Mode runtime and the Tools module, so that the Turn loop and bot layers stay independent of it as ADR 0002 requires.
26. As the founder, I want side effects to stay in the Tools module, so that the repository boundary that Mode definitions carry no side effects still holds.
27. As the founder, I want the model-callable Tools and the Telegram Reminder buttons to share the same Tool classes, so that both surfaces apply identical behaviour.
28. As the founder, I want the runtime to log which Mode handled each Turn, so that I can tell Modes apart when diagnosing a problem.
29. As a developer, I want one way to substitute the model for a Turn in tests, so that I can script Tool calls without reaching into agent internals.
30. As a developer, I want to observe which Tools and instructions the model was offered for a Turn, so that I can prove a Mode's capability boundary through behaviour.
31. As a developer, I want the existing Turn-level test style to keep working, so that the migration does not require a new testing approach.
32. As the Gate A evaluator, I want the Daily Tool schema to be byte-identical before and after the change, so that no declared evaluation evidence is invalidated by a refactor that changed nothing.
33. As the Gate A evaluator, I want the rendered Daily instructions to be byte-identical before and after the change, so that the prompt fingerprint reflects only real behaviour changes.
34. As the Gate A evaluator, I want the evaluation runner to read Daily's Tools through the Mode registry instead of a private framework attribute, so that the runner keeps working as Modes are added.
35. As the Gate A evaluator, I want the invalidating-input list to cover the new modules Daily depends on, so that a change to the runtime or a toolset still forces a new run.
36. As a security reviewer, I want Tool access decided by toolset membership in code rather than by prompt wording, so that a prompt injection cannot grant a Mode a Tool it was not given.
37. As a security reviewer, I want a refused Mode to create no Session Message, Task, Reminder, or outbox entry, so that refusal is side-effect free.
38. As an operator, I want no database schema change in this work, so that it deploys without a protected migration.
39. As an operator, I want no change to runtime configuration defaults, so that every environment behaves as before.
40. As a future Mode author, I want a Mode definition to name the other Modes it may later hand off to, so that handoffs can be added without changing the definition's shape.

## Implementation Decisions

- **Mode definition.** A Mode is a declarative, immutable record with: a unique identifier, a
  participant-facing name, a status (`live`, `planned`, or `disabled`), an instructions builder
  that receives the Turn Context, an ordered set of toolsets, an ordered set of Turn Context
  providers, a required entitlement, a model policy (a primary model reference, with room for
  fallbacks), a set of permitted handoff targets, and a reference to its evaluation suite. Mode
  definitions contain no side effects.
- **Mode registry.** One catalogue registers every Mode at import time. It is deny-by-default:
  resolving an unknown identifier, a `planned` or `disabled` Mode, or a Mode the participant is not
  entitled to results in a refusal, never a fallback to another Mode. Registering a duplicate
  identifier fails.
- **Mode runtime.** A single owned entry point replaces the current handle-message and run-turn
  functions. For each Turn it: resolves the Mode through the routing policy; checks entitlement;
  composes instructions from the Safety Core, the Mode's instructions, and its Turn Context
  providers; loads Session history; runs the model with only the Mode's toolsets; persists the
  user and assistant Messages; maps failures to the existing friendly reply; and records the Mode
  identifier with the Turn. It accepts an optional model override used by tests and the Gate A
  runner. The model framework does not leak past the runtime and the Tools module (ADR 0002).
- **Refusal is side-effect free.** A refused Mode produces a participant-facing refusal message and
  writes no Message, Task, Reminder, receipt, or outbox entry. A failure while choosing the Mode
  (routing or entitlement raising) likewise writes nothing and returns the friendly reply.
- **Safety Core.** The rules every Mode must carry — non-clinical identity, no diagnosis or
  treatment, Crisis Referral, never claiming monitoring or safety, untrusted participant data,
  ownership of identifiers, and emotional conversation never authorizing a Task or Reminder — are
  defined once as verbatim clauses. The runtime guarantees each live Mode's final instructions
  contain every clause: it prepends them unless the Mode's instructions state every clause both
  when rendered with neutral placeholder facts (so participant data cannot stand in for the Mode)
  and when rendered with the real facts (so a Mode whose facts push clauses out still gets them).
  Daily already contains every clause in place, which keeps its instructions byte-identical.
- **Toolsets live in the Tools module.** Tools are grouped by domain — Tasks, Reminders, and
  Later/planning-day — as reusable toolsets. Each Tool builds a CommandContext from Tool Context
  and goes through the shared Commands. The Tool classes remain, because the Telegram Reminder
  button callbacks use them too. Every Tool's name, description, parameter schema, and returned
  text is unchanged.
- **Tool presentation order is declared.** A Mode may pin the order its Tools are presented to
  the model, because models are sensitive to it and Toolsets are grouped by domain rather than by
  presentation. Daily pins the order the single pre-Mode agent used.
- **Registration fails loudly** for a duplicate identifier, a live Mode whose instructions cannot
  render, or a declared Tool order naming a Tool the Mode does not have.
- **Tool authorization is membership.** A Mode can call only Tools in its own toolsets. The runtime
  rejects any Tool call outside them regardless of what the model requests.
- **Turn Context providers are public.** Today's task block, pending Task identifiers, active
  Reminder identifiers, and yesterday's summary become reusable providers with public interfaces.
  No Mode or runtime code calls private Turn Context helpers.
- **Tool Context shape is unchanged in this work.** Narrowing Tool Context per Mode is deferred;
  least privilege in this work comes from toolset membership.
- **Routing policy is a replaceable component.** The initial policy resolves, in order: an
  explicit Mode selection on the Turn, then the default Mode (Daily). Because Daily is the only
  live Mode, no active-Mode persistence is needed yet.
- **Entitlement is a replaceable component.** The initial policy grants every `live` Mode to every
  activated participant. There is no billing or subscription concept.
- **Model policy.** Each Mode names its model. Daily continues to use the configured default model;
  runtime configuration defaults are not changed.
- **Registered Modes.** Daily is `live`. Coach, Reflect, and Recommender are `planned` with their
  purpose declared and no toolsets, so the runtime refuses them.
- **Gate A integration.** The Tool-schema function and the evaluation runner obtain Daily's Tools
  from the registry instead of a private framework attribute. The invalidating-input path list is
  updated to the new import closure of Daily, which the existing import-closure test enforces.
- **No schema change.** No migration is added or modified. The active Mode is not persisted in
  this work, and Session type is not reused as a Mode, because Session types are context metadata
  and not user-selectable Modes.
- **Store sync is unaffected.** No MemoryStore method changes, so the three store implementations
  need no mirroring.

## Testing Decisions

- **What makes a good test here:** it drives the system from the outside and asserts observable
  outcomes — the reply sent, Messages persisted, Tasks and Reminders created or refused, and which
  Tools and instructions the model was offered. It never asserts on registry internals, framework
  attributes, or private helpers, so the internals can be reorganized freely.
- **Seam 1 — the Turn (behaviour).** Tests send a Telegram message through the bot handlers with
  the runtime's model override set to a scripted function model. They assert:
  - Daily's reply, persisted user and assistant Messages, and created Tasks match today's
    behaviour;
  - a scripted `create_task` and `update_task_status` Tool call produce the same Task, Reminder,
    and outbox effects as before;
  - the Tools offered to the model are exactly the live Mode's toolsets;
  - every Safety Core clause is present in the instructions the model receives;
  - a Tool call outside the Mode's toolsets is rejected;
  - a `planned`, `disabled`, unknown, or unentitled Mode is refused with no Message, Task,
    Reminder, or outbox write;
  - a model failure still yields the existing friendly reply and persists it.
- **Seam 2 — contract snapshot (existing).** The Gate A Tool schema and the rendered Daily
  instructions for a fixed Turn Context (fake store, fixed clock) are captured from the
  pre-refactor revision and asserted byte-identical afterwards. This is the proof that Daily did
  not change.
- **Registration invariants** — duplicate identifiers, instructions that cannot render, and a Tool
  order naming unknown Tools — are asserted through the public registration entry point, since they
  fail before any Turn runs.
- **Tests to update.** Tests that imported the old single-agent module now import the Toolsets and
  the runtime. The Tool-class tests stay, because the classes remain.
- **Prior art:** the Turn-level tests that override the model and drive the bot handlers; the
  agent tests that script failures with a failing model; and the Gate A currency tests, including
  the import-closure test that keeps the invalidating-input list honest.
- **Verification before completion:** full backend suite, Ruff, Gate A contract validation, the
  scheduler smoke check, and a clean `git diff --check`.

## Out of Scope

- Building any specialized Mode's behaviour: Coach, Reflect, Recommender, or any other Mode.
- Persisting the active Mode, and any database schema change or migration.
- Dashboard Mode selection, or changing the Mode chips.
- Automatic or classifier-based routing, and agent-initiated handoffs.
- Mode-to-Mode delegation, multi-step workflows, and durable execution.
- A Memory service or cross-Mode data sharing.
- Model fallback across providers, and per-Mode model differences beyond the declaration.
- Billing, subscriptions, payments, or real premium entitlements.
- Exposing or consuming agents and Tools over MCP or A2A.
- OpenTelemetry tracing and per-Mode cost dashboards.
- Per-Mode evaluation CI.
- Narrowing Tool Context per Mode.
- Changing how Tool dependency failures are reported to the model.
- Interaction Style.

## Further Notes

- **Phased follow-ups.** This is Phase 1 of five. Phase 2 adds model policy with fallback,
  tracing, per-Mode evaluation, and real entitlements. Phase 3 adds Coach as the first second Mode
  with explicit routing, active-Mode persistence (a protected migration), and confirmed handoffs.
  Phase 4 adds classifier routing, a Memory service, and delegation. Phase 5 adds durable workflows
  and MCP/A2A integration. Each should get its own spec. Specs were filed on 2026-09-26 as
  issues 02 (Phase 2), 03–04 (Phase 3), 05–07 (Phase 4), and 08–09 (Phase 5). Real entitlements
  moved from Phase 2 to issue 03.
- **Recorded decisions.** The founder has asked that recorded product decisions not limit the
  architecture. This foundation encodes policy as configuration, so it neither enforces nor
  bypasses them: decision 14's exclusion of automatic routing becomes a routing-policy choice,
  decision 12's exclusion of feature tiers becomes an entitlement-policy choice, and the Modes that
  exist remain a registration choice. Decision 15's prohibition of a Therapy Mode stays in force
  until it is explicitly reopened; nothing here registers such a Mode.
- **Repository guardrails respected.** Side effects stay in the Tools module, the model framework
  stays behind an owned interface (ADR 0002), no migration and no runtime-configuration default
  changes, and no store method changes.
- **Timing.** No declared Gate A run exists yet. Doing this before that run means the evaluation is
  paid for once; doing it afterwards would invalidate the run and require another.
- **Proposed glossary additions** for CONTEXT.md: *Mode Definition* (the declared record behind a
  Mode), *Toolset* (a reusable group of Tools), and *Safety Core* (the clauses every Mode must
  carry).

## Comments

### 2026-09-24 — Implemented locally; independent review pending

A live defect was found while capturing the Daily golden snapshot. The agent used a Pydantic AI
system prompt, which is injected only when a run starts with empty history. Every Turn after the
first in a Session starts with history, so from the second message onward the model received no
instructions at all: no non-clinical or Crisis Referral rule, no untrusted-input rule, no pending
Task identifiers, and no current time. Gate A could not see it: only 4 of 60 cases carry prior
history and none of the 14 `safety_boundary` cases do. The runtime now uses instructions, which
are re-sent on every request and never stored in history. A standalone one-line hotfix for the
pre-refactor code was prepared separately so it can ship before this work.

Implementation matches this spec with two corrections applied above: the Tool classes are kept
for the Reminder button callbacks, and the instructions-delivery fix is a deliberate behaviour
change.

`FakeStore.get_pending_reminders` omitted the `tasks(title, category)` join that `MemoryStore` and
`InMemoryStore` return, so any Turn-level test with an active Reminder crashed while building
instructions. It now mirrors production.

Verification:

- Seam 2: Daily's Tool schema hash is unchanged at
  `0021a942df260e3fdb17b0ab6ee8d0dae09c1697349a99c5396ea7dcdb165013`, and Daily's rendered
  instructions for a populated fixed Turn Context are identical to the pre-refactor capture after
  generated identifiers are made positional.
- Seam 1 covers offered Tools, the Safety Core for Modes that do and do not state it, participant
  data unable to stand in for the Safety Core, out-of-Toolset Tool calls, refusal of planned,
  unknown, and unentitled Modes with nothing written, an entitlement policy unlocking a Mode,
  and the friendly failure reply.
- All 11 mutants of the guarantees fail at least one test. Reordering Daily's context sections
  initially survived because the fixture had no yesterday summary; the fixture now populates every
  section.

Known follow-up, out of scope: the Turn Context computes "today" and "yesterday" from the real
clock inside the stores rather than from the injected Clock, so a fixed evaluation clock and the
Task lists can disagree about the date.

### 2026-09-25 — Independent review: changes required, all addressed

The independent review verified the Daily behaviour, the instructions-delivery fix, Tool
authorization, refusal, Gate A integration, layering, and the FakeStore shape. It refuted two
claims, and was right to:

- **The tests pinned too little.** 16 of its 17 mutants survived, including a `disabled` Mode
  running, Session history being dropped or duplicated, the model override never resetting, and
  retry budgets changing. The spec-required disabled-Mode test was missing.
- **The Safety Core check could be bypassed.** It ran only on a placeholder render, so a Mode whose
  real facts pushed clauses out of its instructions (for example, a length budget with a long name)
  lost the Crisis Referral rule.

It also found three further defects:

- The model was offered Daily's Tools in a different order from before, which the name-sorted
  schema hash and the test harness both hid.
- The spec's "fail loudly at registration" never happened: a live Mode whose instructions raise
  registered successfully and failed only on a participant's first Turn.
- A failure while choosing the Mode wrote a failure reply into the Session with no user message
  before it.

Fixes:

- A Mode may declare `tool_order`, and Daily pins the pre-Mode order.
- The Safety Core is supplied unless both the placeholder render and the real render state every
  clause.
- Registration renders live Modes and rejects a `tool_order` that names unknown or repeated Tools.
- Resolution failures write nothing.
- 16 behaviour tests were added, and the test harness now records Tool order unsorted.

Mutation testing then flagged four more survivors:

- One was a harness miscount: collection errors were not counted.
- One was a malformed mutant. It exposed that duplicate `tool_order` entries were silently
  accepted, which is now rejected.
- Toolset membership was unpinned for single-Toolset Modes, and is now tested.
- The profile-versus-Turn timezone was caught only during six hours of each day. The golden fixture
  now uses `Pacific/Kiritimati` against `Etc/GMT+12`: 26 hours apart, so their dates never
  coincide.

All 32 mutants, including the reviewer's 17 and a revert of each fix, now fail at least one test.

The checked-in golden is now **HEAD's own output**, not the new code's. It was captured from a
temporary worktree of the pre-Mode revision with the instructions hotfix applied, and the new
runtime reproduces it exactly: prompt and Tool order both.

Verification: 519 backend tests, Ruff, Gate A contract validation, scheduler smoke, CLI and callback
imports, and `git diff --check` including untracked files.

### 2026-09-25 — Re-review passed; remaining items closed

The independent re-review returned **PASS**. All seven original findings were fixed, and the fixes
introduced no regressions. The reviewer independently confirmed against HEAD, with the
instructions hotfix applied:

- identical prompts on two Turns;
- identical Tool definitions and presentation order;
- identical retry behaviour for bad arguments and unknown Tools;
- a golden rebuilt on HEAD that matches the checked-in one exactly.

Its one should-fix and four nits are closed:

- `run_turn`, which Gate A calls directly, now has its own refusal test. Before, a mutant that
  skipped authorization there survived.
- A Mode that trims its own instructions can no longer let a participant's name stand in for its
  clauses. Before the real-render check, participant values long enough to hold a clause (at least
  87 characters) are removed. Removal can only cause the Safety Core to be prepended. Shorter
  values are left alone, so a name like "Amigo", which appears inside a clause, does not change
  Daily's instructions.
- Registration rejects a Tool name that appears in more than one Toolset.
- The `safety.py` docstring now describes the check the code actually runs.
- New tests cover:
  - unlisted Tools following a partial order;
  - registration rejecting an empty render;
  - a `tool_order` over a Toolset that cannot list its Tools;
  - the Safety Core header;
  - the whole within-budget Session history reaching the model.

Every new guard's mutant fails at least one test. The reviewer also found nine surviving mutants
inside Tool bodies: idempotency-key formats, guards, and reply text. The same nine survive against
HEAD's original agent, so these are gaps that predate this work and are not caused by it. They are
recorded here as a follow-up; the Tool bodies were moved without edits.

Verification:

- 529 backend tests pass with no warnings.
- Ruff, Gate A contract validation, and the scheduler smoke check pass.
- CLI and callback imports succeed.
- `git diff --check`, including untracked files, is clean.

### 2026-10-03 — Current-baseline review findings fixed; independent re-review pending

The review against the current `develop` baseline found five gaps. This implementation pass fixes
all five while leaving the issue open until a different agent independently reviews and verifies
the result:

- Session transcript loading and persistence, plus friendly failure persistence, now belong to
  `SessionTurnOrchestrator` in `src/turns.py`. `ModeRuntime` resolves, authorizes, composes, and
  executes without writing Session Messages; Pydantic AI remains behind owned history/result
  types.
- New ordinary policy, registry, runtime, and Turn-orchestrator methods are asynchronous.
  Constructors, dataclass validation, and the registry's synchronous magic methods remain the
  documented idiomatic exceptions.
- `requested_mode=None` alone selects Daily. An explicitly supplied empty identifier is resolved
  as unknown and refused before any Session, Task, Reminder, receipt, or outbox write.
- Gate A obtains Daily through `build_registry()["daily"]`; a regression test replaces the
  registry to prove the schema function does not read the `DAILY` constant directly. The runner
  uses the shared transcript-owning Turn orchestrator.
- A Turn-level scripted `update_task_status` regression now proves the Task transition, active
  Reminder cancellation, durable cancellation outbox effect, participant reply, and Session
  transcript together.

Implementation verification before re-review:

- 533 backend tests passed.
- Ruff passed for `src`, `tests`, and `scripts`.
- Gate A contract validation passed: 60 cases, 3 repetitions.
- Scheduler smoke check passed.
- CLI, Reminder callback, and Toolset imports passed.
- `git diff --check` and the same whitespace check over every untracked file passed.

No migration, `.env`, `src/config.py`, `src/db/supabase.py`, or smoke-check implementation was
changed. Daily's prompt golden, Tool schema hash, and Tool presentation order remain unchanged.

### 2026-10-03 — Independent standards/spec verification passed; issue closed

A different agent independently reviewed the complete tracked and untracked change set against
`develop` baseline `b2dc1cd`. Standards and specification both passed, with all five current-review
findings resolved and no new actionable findings.

The reviewer reconstructed the baseline Daily instructions and confirmed exact equality with the
current output and checked-in golden. It also compared baseline Tool schemas, presentation order,
and moved Tool/helper bodies and confirmed they are unchanged. Session persistence, failure
handling, async interfaces, empty-identifier refusal, registry-based Gate A schema capture, and the
Turn-level Task/Reminder/outbox resolution test were verified directly. Safety Core composition,
refusals, history, override reset, retries, Tool membership, callback reuse, and registration
invariants were reviewed.

Independent verification: 533 backend tests passed; Ruff, Gate A 60-case/3-repetition validation,
scheduler smoke, and CLI/callback/Toolset imports passed. Tracked diff and every untracked file
passed whitespace checks. This closes the Modular Mode Foundation only; subsequent Mode issues
and the separate release gates retain their own requirements. Changes remain uncommitted.
