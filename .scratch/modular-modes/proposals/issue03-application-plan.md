# Issue 03 application plan — commands first, recoverable handoffs later

Status: read-only readiness proposal; implementation not authorized by this document
Prepared: 2026-10-03

Migration 016 and the Store contract are foundations, not participant-facing Mode switching.
Daily remains the only live production Mode. Coach, Reflect, and Recommender must stay `planned`.

## Slice A — explicit Session Mode commands and routing

Implement this before any handoff Tool or callback:

1. Add required participant-facing `limits` to `ModeDefinition`; require nonempty limits for live
   Modes. This declaration must not enter the model instructions or Tool schema. Approve the exact
   `/mode`, entry, exit, refusal, and withdrawal copy before release.
2. Replace string-only routing with an owned selection value carrying `mode_id` and `entered_by`
   (`explicit`, `session`, or `default`). `ExplicitThenSessionThenDefault` reads the Session Mode;
   `None` means no explicit request, while `""` remains an explicit unknown Mode refusal.
3. Add `GrantedParticipants`: `activated` Modes remain available to activated participants;
   `grant` Modes require the Store's current active grant. Unknown entitlement values fail closed.
4. Keep all mutations outside `src/agent/`. A top-level application Mode controller authorizes a
   registry definition, derives `grant_required` from that trusted definition, and calls
   `set_active_mode`. Neither a command nor a model supplies that Boolean.
5. Parse exact `/mode`, `/mode <id>`, and `/daily` commands in `TurnProcessor` after Session
   acquisition and before model execution. Commands make no model call and write no Session
   Message. `/mode` lists only live, entitled definitions; in production that is Daily only.
   Planned, unknown, and ungranted entries are refused without changing Session state.
6. Ordinary Turns resolve explicit → Session → Daily. If a Session-selected Mode is no longer
   registered live or entitled, `SessionTurnOrchestrator` clears it through the Store and sends
   only the approved withdrawal notice. It must not persist or process that participant message
   in Daily; the participant can resend it. A fresh Session's null `active_mode_id` routes Daily.
7. Add `entered_by` to content-free Turn telemetry with a deliberate telemetry schema revision.
   Command-only responses are not model Turns; if command audit is required, give it a separate
   content-free event rather than fabricating model usage.

Tests should use one test-only live `entitlement="grant"` Mode. Cover entry, Session persistence,
exit, new-Session reset, planned/unknown/ungranted refusal, expiry/revocation withdrawal, the
three Store implementations, zero model calls and zero transcript writes for commands/refusals,
and unchanged Daily instructions, Tool order/schema, and model policy.

Actual integration gaps found:

- `RoutingPolicy.select` currently returns only a string, so it cannot populate `entered_by` or
  distinguish a broken Session selection from an explicit refusal.
- `ToolContext` carries only `session_id`, not the loaded Session; routing must use the Store or an
  explicitly supplied immutable Session fact rather than reaching into bot state.
- `ModeRuntime.resolve` owns authorization but cannot clear Session state because `src/agent/`
  must remain side-effect free. The orchestrator/application controller must own withdrawal.
- `BotHandlers.handle_callback` sends every non-onboarding callback to `ReminderActions`; future
  Mode callbacks require a distinct, prefix-based dispatcher. Generic channel buttons already
  work in Telegram and CLI, so no protocol change is needed.

## Slice B — handoff proposal and decline only

After Slice A passes, add the Handoffs Toolset only to a test Mode with declared targets. The Tool
derives source/target entitlement flags from the registry, rejects undeclared targets, calls
`create_handoff`, and sends approved Confirm/Decline buttons through `MessageChannel`. Daily gets
no Handoffs Toolset, preserving its schema. Dispatch a reserved callback prefix to a dedicated
application action; resolve ownership from the authenticated chat, never callback payload fields.
Decline, expiry, replay, cross-participant tap, revoked grant, and changed source Mode must perform
no target Turn and no Task/Reminder side effect.

## Blocked Slice C — confirmed target Turn

Do not ship confirmation-to-execution on migration 016 alone. Its RPC atomically marks a handoff
`confirmed` and changes the Session Mode, but it has no durable execution state or claim. If the
process dies after confirmation and before/during the target Turn, Telegram's durable update claim
will reject the redelivery and the carried request is lost. Resolving after the model Turn instead
allows concurrent taps to run it more than once.

A separately approved additive migration is needed before this slice. At minimum it must model a
confirmed handoff's execution status, durable claim/lease, attempts, completion, and content-free
failure code, with a service-only claim/recovery RPC. Recovery must use a stable handoff Turn id.
That alone does not guarantee exactly one model-selected side effect: a crash after a Tool commits
but before execution completion can rerun a nondeterministic model plan. The design must therefore
also approve either (a) durable Tool-call receipts keyed by handoff and stable call ordinal with
argument-conflict refusal, or (b) a deterministic confirmed-command representation executed
without replanning. Existing Telegram update claims are insufficient.

Only after that design, migration approval, and crash-injection tests should confirmation run one
Daily Turn. The carried request remains untrusted participant-confirmed data, never instructions
or authorization. Tests must crash at each boundary (after confirmation, after claim, after Tool
commit, before completion) and prove recovery creates exactly one Task and no duplicate Reminder.

## Explicitly not enabled

No planned production Mode changes status; no dashboard selector, automatic routing, grant CLI,
Coach/Reflect/Recommender behavior, production deployment, or participant handoff copy is approved
by this plan.
