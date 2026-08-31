# Apply Later Consistently Across Both Surfaces

Status: closed
Label: `ready-for-agent`
Severity: `severity:high`
Type: AFK
Owner: unassigned

## What to build

Implement the single Later policy through the shared command path. Telegram and dashboard both
acknowledge the current Reminder, keep its Task pending, and create the policy-defined replacement
with a durable scheduler effect.

## Acceptance criteria

- [x] The first Later creates a replacement 60 minutes later and the second creates one 30 minutes
  later.
- [x] The third Later moves the Task to the next local Planning Day and creates a replacement at
  wake time.
- [x] Quiet-hour adjustment applies to every automatic delay and the response states the exact
  next local delivery date, time, and timezone.
- [x] Later acknowledges the current Reminder and never resets a terminal Reminder to `pending` or
  uses `deferred` as a Task state.
- [x] Telegram and dashboard produce identical outcomes under replay, stale actions, scheduler
  outage, and cross-midnight conditions.

## Blocked by

- [Schedule a Reminder Through the Durable Outbox](05-schedule-reminder-through-durable-outbox.md)

## Delivery notes

- Affected areas: Later policy, command service, Telegram callbacks, dashboard controls, outbox,
  Task/Reminder presentation, and tests.
- Rollout: verify all three policy steps and quiet-hour cases in staging before replacing the
  dashboard's legacy fixed delay.
- Rollback: disable the action while preserving existing pending replacement Reminders; do not
  restore in-place Reminder rewinds.

## Comments

### 2026-08-31 — Claimed

Implementation started after issue 06 closed. The existing in-place Telegram snooze and fixed
dashboard delay will be replaced by one policy and shared idempotent command before any protected
database proposal is presented for review.

### 2026-08-31 — Migration review requested

- One deterministic `LaterPolicy` now applies +60 minutes, +30 minutes, then the next local
  Planning Day at wake time, with automatic quiet-hour adjustment.
- Telegram and dashboard use one `ApplyLaterCommand`; both return the exact next local date,
  time, and timezone, and the dashboard's fixed 15-minute path is removed.
- FakeStore and InMemoryStore acknowledge the current Reminder, retain the pending Task, create a
  replacement row, increment deferral/version state, and persist stable cancel/schedule effects.
- Replay, repeated/stale/wrong-owner actions, scheduler outage, cross-midnight quiet hours, all
  three steps, and adapter behavior are covered.
- The protected database proposal is available at
  [Review: Atomic Later Command Migration 008](../reviews/008-atomic-later-command.md).
- Pre-migration verification passes with 163 Python tests, Ruff, dashboard lint/build, and
  `git diff --check`.
- The exact proposal passes PostgreSQL 15 after migrations 001–007 with live three-step Later,
  replay, active-Reminder monotonicity, Planning Day, deferral/version, one-active uniqueness,
  six-effect durability, and client privilege assertions.

### 2026-08-31 — Completed

- The project owner approved Migration 008 before `migrations/008_atomic_later_command.sql` was
  added; the file matches the reviewed SQL apart from its normal final newline.
- CI now applies all eight migrations and proves the three-step sequence, exact replay, conflicting
  payloads, stale versions/steps, tenant isolation, Planning Day movement, one-active uniqueness,
  six durable effects, and service-only execution against PostgreSQL 15.
- Telegram and dashboard no longer use in-place or fixed-delay snooze paths. Both acknowledge the
  current Reminder, preserve the pending Task, create the policy replacement, and report its exact
  local date, time, and timezone.
- Final verification passed with 163 Python tests, Ruff, dashboard lint/build, the exact
  eight-migration PostgreSQL sequence, and `git diff --check`.
