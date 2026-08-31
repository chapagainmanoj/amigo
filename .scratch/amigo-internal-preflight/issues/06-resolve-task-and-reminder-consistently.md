# Resolve a Task and Reminder Consistently

Status: closed
Label: `ready-for-agent`
Severity: `severity:high`
Type: AFK
Owner: unassigned

## What to build

Implement shared Done, Skip, and Cancel commands so Telegram callbacks and dashboard controls
produce the same tenant-owned, idempotent terminal outcome. Resolving a Task also records the
corresponding Reminder transition and durable cancellation effects.

## Acceptance criteria

- [x] Done transitions the Task to `completed`; Skip transitions it to `skipped`; Cancel
  transitions it to `cancelled`.
- [x] Every terminal Task outcome cancels remaining active Reminders through durable outbox
  effects.
- [x] A sent Reminder becomes `acknowledged` when acted upon, and no terminal Task or Reminder row
  returns to an active state.
- [x] Repeated buttons, command replay, stale versions, and wrong-owner identifiers cannot create a
  second transition or leak resource existence.
- [x] Telegram and dashboard behavior is verified through the same command contract and resulting
  dashboard state.

## Blocked by

- [Schedule a Reminder Through the Durable Outbox](05-schedule-reminder-through-durable-outbox.md)

## Delivery notes

- Affected areas: resolution commands, Tools, Telegram callbacks, dashboard controls, outbox
  cancellation, Store implementations, and integration tests.
- Rollout: stage behind the new command endpoints and verify old callbacks remain safely
  idempotent during deployment.
- Rollback: disable new adapters and retain canonical terminal states; never reactivate resolved
  rows automatically.

## Comments

### 2026-08-31 — Claimed

Implementation started after issue 05 closed. The shared terminal-resolution command and Store
parity will be established first, then Telegram/dashboard adapters and any protected database
proposal will be reviewed and verified against the same contract.

### 2026-08-31 — Migration review requested

- Done, Skip, and Cancel now use one `ResolveTaskCommand` across agent turns, Telegram Reminder
  callbacks, and dashboard controls; every adapter injects the authenticated actor.
- FakeStore and InMemoryStore atomically transition the Task, acknowledge an acted sent Reminder,
  cancel other active Reminders, persist stable cancel effects, and store replayable results.
- Exact replay, conflicting keys, repeated buttons, stale dashboard versions, conflicting
  terminal outcomes, cross-tenant identifiers, and all three terminal states are covered.
- Dashboard terminal controls no longer write or delete Task rows directly and never reactivate a
  terminal Task.
- The protected database proposal is available at
  [Review: Consistent Task and Reminder Resolution Migration 007](../reviews/007-consistent-task-reminder-resolution.md).
- Pre-migration verification: 155 Python tests, Ruff, dashboard lint/build, and the Migration 006
  PostgreSQL CI sequence pass.
- The exact proposal also passes PostgreSQL 15 from migrations 001–006 with live assertions for
  atomic completion, sent-Reminder acknowledgement, replay, repeated outcomes, stale versions,
  conflicting terminal outcomes, tenant ownership, and browser/service privilege boundaries.

### 2026-08-31 — Completed

- The project owner approved Migration 007 before
  `migrations/007_consistent_task_reminder_resolution.sql` was added; the migration matches the
  reviewed SQL apart from its normal final newline.
- CI now applies all seven migrations and proves all terminal outcomes, exact replay, payload
  conflict rejection, stale-version rejection, terminal monotonicity, tenant isolation, and
  browser/service privilege boundaries against PostgreSQL 15.
- Telegram Reminder buttons and dashboard Done/Skip/Cancel controls use the same command.
  Dashboard controls no longer reactivate, directly update, or delete Task rows.
- Final verification passed with 155 Python tests, Ruff, dashboard lint/build, the exact
  seven-migration PostgreSQL sequence, and `git diff --check`.
