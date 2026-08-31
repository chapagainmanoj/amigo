# Schedule a Reminder Through the Durable Outbox

Status: closed
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: unassigned

## What to build

Let Telegram and dashboard schedule or reschedule an owned Task's Reminder through one atomic
command. Persistence records the canonical Reminder transition and a durable scheduler effect in
the same transaction so temporary scheduler failure cannot lose accepted intent.

This slice requires review of the Reminder, command, and scheduler-outbox migration and database
functions.

## Acceptance criteria

- [x] Schedule, reschedule, and cancel operations resolve the actor server-side and use one shared
  domain command from Telegram and dashboard.
- [x] A successful transaction atomically records Reminder state, aggregate version, command
  receipt/result, and every required scheduler-outbox effect.
- [x] Each Task has at most one active Reminder; rescheduling cancels the prior Reminder and creates
  a replacement rather than rewinding a terminal row.
- [x] A committed command with queued effects returns `202 Accepted` with the canonical result,
  version, exact intended time, and effect state.
- [x] Outbox replay uses stable effect/job identities and cannot create duplicate jobs or
  cross-participant scheduling.
- [x] All Store implementations and failure-injection tests preserve equivalent behavior.

## Blocked by

- [Capture an Inbox Task Through One Shared Command](04-capture-inbox-task-through-shared-command.md)

## Delivery notes

- Affected areas: Reminder lifecycle schema, transactional functions, scheduler outbox, commands,
  Store implementations, scheduler projection, and integration tests.
- Rollout: enable the worker in staging, reconcile existing pending Reminders, then switch adapters
  to the command path.
- Rollback: stop command intake and the worker while retaining durable effects for a reviewed
  forward-fix; do not discard accepted scheduling intent.

## Comments

### 2026-08-30 — Claimed

Implementation started after issue 04 closed. The shared Reminder commands, Store parity, and
outbox worker will be built before presenting the protected Reminder/outbox migration and service
functions for explicit human review.

### 2026-08-30 — Migration review requested

- Telegram and dashboard adapters now use shared Schedule, Reschedule, and Cancel Reminder
  commands with server-injected participant identity.
- FakeStore and InMemoryStore atomically record canonical Reminder transitions, Task versions,
  receipts, and stable scheduler effects; exact replay and payload conflicts are covered.
- The scheduler-outbox worker claims effects, applies stable `user_id:reminder_id` jobs, records
  completion, and retains temporary failures for replay.
- Dashboard scheduling adapters return `202 Accepted`; the existing snooze UI now calls the
  reschedule command instead of writing Reminder rows directly.
- Failure-injection, ownership, active-Reminder uniqueness, replacement-row, and API tests pass
  across in-memory implementations.
- The exact database proposal is available at
  [Review: Durable Reminder Outbox Migration 006](../reviews/006-durable-reminder-outbox.md).
- Pre-migration verification: 142 Python tests, Ruff, dashboard lint/build, and
  `git diff --check` pass.
- The proposed SQL passed PostgreSQL 15 clean-schema and representative previous-schema checks.
  Live assertions covered schedule/reschedule/cancel replay, conflicting keys, tenant ownership,
  one-active-Reminder uniqueness, exact queued results, exclusive outbox claims, completion, and
  browser-role revocation. The legacy check preserved duplicate rows while cancelling all but the
  newest active Reminder and backfilled canonical state and intended-time metadata.

### 2026-08-31 — Completed

- The project owner approved the exact Migration 006 proposal before it was added as
  `migrations/006_durable_reminder_outbox.sql`; the migration differs only by its normal final
  newline.
- CI now seeds duplicate legacy active Reminders, proves canonical backfill and one-active
  uniqueness, and exercises live schedule/replay/reschedule/cancel plus exclusive outbox
  claim/completion.
- The tenant matrix proves authenticated clients cannot directly update Reminders, inspect the
  scheduler outbox, or invoke service-only Reminder RPCs.
- PostgreSQL 15 passed the exact six-migration CI sequence from an empty database. Verification
  also passed with 142 Python tests, Ruff, dashboard lint/build, and `git diff --check`.
- README and the implementation status now document Migration 006 and the durable scheduling
  boundary.
