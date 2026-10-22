# Issue 08 — durable workflow primitives using the existing outbox

Status: provisional — owner review
Date: 22 October 2026
Implementation: Coach declaration and owned read model, reusing 018/019; no new infrastructure.
Sources: Issue 08; Coach contract; build-plan Phase 6; proposed 018/019 lifecycle/delivery patterns.

## Decision

Reuse PostgreSQL state, the scheduler, command receipts and the 019 proactive ledger/outbox. Do not
adopt an external workflow engine. No evidence has been supplied that these mechanisms are
insufficient, and the issue explicitly asks to use Coach's trial evidence before generalizing.
Software implementation or a candidate eval is not trial evidence.

First express the existing Coach weekly review/check-in loop as a declared sequence over its
owned Program and delivery records. Do not introduce a second independent lifecycle for the same
program. A small typed workflow specification can name a version, steps, wait conditions and
participant-confirmation points while an adapter maps them onto the existing aggregate/outbox.
General Store workflow tables should be added only when a demonstrated second flow cannot be
represented without duplicating those primitives; record that evidence before expanding.

## Required execution semantics

- Stable identity: user + aggregate ID + workflow definition version + step ID + occurrence key.
  Store input references and approved command manifests, not arbitrary executable code or hidden
  copies of sensitive conversations. Changes to a definition cannot silently reinterpret a run.
- A claimed step uses a fenced lease. Completion checks the current token after lock acquisition.
  Lease ownership alone is not an exactly-once side-effect guarantee.
- Before a Tool runs, persist its approved deterministic plan/arguments. Recovery reuses the same
  plan, aggregate/Session identity, frozen interpretation clock and command idempotency key. Never
  replan a previously committed step because a process restarted.
- A wait is durable metadata: owner, aggregate/version, step, waiting-for kind, earliest resume
  time, expiry, state and an opaque confirmation token/hash where needed. Restart cannot turn a
  wait into consent. An incoming message may wake only its owner's declared wait.
- Participant confirmation binds exact visible action and current version. Resolve it atomically;
  decline, expiry, cross-owner callbacks and repeats do nothing. No side effect occurs merely
  because a timer fires or a model returns a requested Tool call. A previously approved Program
  cadence may supply bounded standing authorization for its check-ins; a new decision or changed
  cadence still needs fresh confirmation, and pause/withdrawal/expiry revokes that authorization.
- Dispatch still rechecks current grant/consent, active Program, quiet hours, the shared daily
  budget and the current delivery endpoint. Pause/Stop/withdrawal/deletion cancel queued work.
  After one missed check-in follow-up, suppress weekly reviews too until participant reply.
- Provider timeout/unknown acceptance is an uncertain delivery. Do not blindly resend or describe
  it as exactly once; use the existing conservative delivery/recovery policy and expose the
  content-free outcome for operator review.

## Rights and verification

Workflow state must be visible through the owning feature's inspection/export path and be removed
with it. Include outbox payloads, manifests, receipts, confirmation metadata and caches in deletion;
retain only approved content-free proof. No new retention or privacy promise is made here.

Required tests force crashes before/after wait persistence, after confirmation, before/after Tool
commit, and before completion. Concurrent workers and double callbacks must preserve one approved
logical transition; command receipts must prevent repeated Task/Reminder effects. Test cancellation,
expiry, budget collisions and both messaging capability paths. Keep provider-delivery uncertainty
separate from deterministic database idempotency in the evidence report.

The Phase 6 implementation may consolidate shared primitives once Phase 5 is complete. External
engine adoption remains unapproved unless concrete insufficiency is demonstrated and its hosting,
secrets, processor and operating implications receive a separate decision.

## Proposed implementation contract after Phase 5

This is a contract for review, not authorization to implement a generic workflow layer. Issue 08's
explicit prerequisite remains unmet: no Coach trial has demonstrated scheduler/outbox insufficiency.
Phase 5 completion alone does not meet that prerequisite. The default disposition is to retain the
existing implementation and document its mapping; any consolidation must preserve the guarantees
below without adding a second lifecycle or participant-visible promise.

| Declared step or wait | Existing durable owner and operation |
| --- | --- |
| Draft awaiting explicit approval | 018 Program `draft`, current version and expiring approval token |
| Approval accepted | `confirm_coaching_approval(user_id, token, idempotency_key, payload_hash)` atomically activates and receipts the transition |
| Cadence waiting until a selected slot | Active Program configuration plus deterministic `plan_coaching_delivery`; restart recomputes the same eligible occurrence |
| Check-in, follow-up or weekly review ready | `enqueue_coaching_delivery(user_id, program_id, expected_version, delivery_key, local_day, kind, scheduled_at)` reserves budget and inserts at most one Program/local-day occurrence |
| Worker lease | `claim_coaching_deliveries(worker_id, limit)` yields a fenced claim token |
| Current authorization checked before send | `mark_coaching_dispatch(user_id, delivery_key, claim_token)` plus the worker's fresh profile, consent, Activation, endpoint and plan checks |
| Send outcome | `finish_coaching_delivery(user_id, delivery_key, claim_token, outcome)` records accepted/uncertain/cancelled; uncertain dispatch is never blindly repeated |
| Waiting for participant reply | Persisted deliveries plus `note_coaching_reply(user_id, program_id)`; two unanswered accepted/uncertain/dispatched messages suppress every cadence kind |
| New decision at review | Explicit existing coaching command and optimistic Program version; a model response or timer cannot confirm it |
| Stop, expiry or rights request | Program lifecycle cancellation, due completion, and existing Coach export/delete operations |

No migration or additional Store API is proposed for this first mapping. The delivery key remains
`coach:{program_id}:{local_day}`, preserving the already stored identity and one-occurrence/day
constraint. Program IDs are owned; row claims include owner and token. A declaration version, if
introduced later, must never rewrite this key for existing Programs or cause an old occurrence to
be sent again. Existing Programs need a pinned interpretation or explicit version migration before
any changed cadence semantics can apply.

If a second approved flow demonstrates an actual missing durable wait, the next proposal must name
that exact wait and show why these records cannot represent it. A minimal additional wait would
need owned aggregate ID/version, definition version, stable step/occurrence key, explicit typed
condition, earliest resume/expiry, opaque hashed confirmation token, current state and fenced
transition receipt. Store resolve would atomically check owner, version, expiry and single use.
Its API and migration remain deferred; arbitrary Tool execution, model-generated executable plans
and implicit cross-Mode context copies are excluded from that proposal.

Acceptance evidence for consolidation: keep current planner/DST/quiet-hour/budget/reply-suppression
tests; force process replacement after enqueue and before claim, after claim before dispatch, after
dispatch before finish, and after accepted finish before reconcile. Assert one database occurrence,
no retry of uncertain provider sends, stale-token refusal, independent owner boundaries, restart
preservation of approval expiry and no automatic continuation after decline/pause/withdrawal.
For Task/Reminder-producing steps, additionally force a crash after the Command receipt commits and
prove replay returns that same receipt without a second effect. Existing message delivery tests
cannot substantiate this separate Tool guarantee.


## Implemented slice — 22 October 2026

Owner authorized Phase 6 implementation after Phase 5. `src/workflows.py` declares immutable Coach
workflow v1 and projects the existing owned Program/delivery/reply records. The authenticated
`GET /api/coaching/workflow` endpoint exposes that metadata without goals, progress, approval
secrets, execution tokens, command payloads or provider messages. Inspection never claims a lease,
resumes a wait, changes consent or executes a Tool. Draft, pause and terminal states explicitly
require approval/resume or advertise no continuation. No new migration or Store API was needed.

`tests/test_workflows.py` replaces the worker after enqueue, claim, dispatch marker and accepted
finish on both threaded and unthreaded channels. One owned occurrence remains; expired claim
recovery fences the old token, accepted sends do not repeat, and unknown provider acceptance
becomes uncertain without resend. Additional cases preserve draft nonapproval, owner boundaries,
metadata privacy and the two-unanswered wait across worker replacement until the owner's reply.
The tests use persisted local Store state across worker instances, not an operating-system kill
or a fresh PostgreSQL connection. SQL durability remains supplied by the existing reviewed 018/019
records and assertions; no new generic execution guarantees are claimed.

The declaration version is explicitly `current_code_only`, not a version persisted per Program.
Only v1 exists. A future v2 requires a separate explicit binding/migration decision before altering
existing Program interpretation or occurrence keys. This slice supplies no arbitrary workflow
runner, no durable arbitrary Tool manifest and no claim of exactly-once provider delivery. Existing
Coach Program Commands and the 019 worker remain the executors. Task/Reminder-producing workflows
remain outside this declaration and require their own persisted plan plus command-receipt proof.
No trial evidence or external-engine insufficiency has been manufactured.


Final repository validation: 16 new workflow tests passed (including both local Stores for draft
inspection/deletion). Combined workflow/delivery/lifecycle/Mode tests: 126 passed in 1.31s. Targeted
Ruff and `git diff --check` passed. Declaration is attached through `ModeDefinition.workflows` to
Coach only; cross-Mode and duplicate attachments fail. Daily has no workflow declaration and its
existing instructions/schema golden tests pass unchanged. Endpoint sets `Cache-Control: no-store`.
Files: src/workflows.py, src/agent/modes.py, src/agent/catalogue.py, src/api/coaching.py,
tests/test_workflows.py, and this provisional record. No protected file, Store or migration edit
in this Issue08 slice. Parent owns the final Gate A fingerprint update and combined verification.
