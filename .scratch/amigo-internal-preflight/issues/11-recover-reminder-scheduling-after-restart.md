# Recover Reminder Scheduling After Restart

Status: closed
Label: `done`
Severity: `severity:high`
Type: AFK
Owner: unassigned

## What to build

Treat the database as Reminder authority and APScheduler as a rebuildable projection. Startup,
outbox replay, and periodic reconciliation restore missing or wrongly timed jobs and remove jobs
that no longer correspond to an active owned Reminder.

## Acceptance criteria

- [x] Startup reconstructs exactly one stable scheduler job for every canonical Reminder that
  requires future delivery.
- [x] Reconciliation repairs missing or wrongly timed jobs and cancels jobs for missing, terminal,
  or wrong-owner Reminders.
- [x] Outbox effects use atomic claims, bounded retries, stable identities, and a visible poison
  state rather than disappearing after repeated failure.
- [x] A Reminder no more than 15 minutes late is delivered at most once with delayed timing;
  anything older becomes missed while its Task remains pending.
- [x] Recovery emits at most one summary rather than a burst of stale Reminder messages.
- [x] Restart, interrupted outbox processing, scheduler outage, duplicate effect, and inverse-drift
  cases converge under automated failure injection.

## Blocked by

- [Schedule a Reminder Through the Durable Outbox](05-schedule-reminder-through-durable-outbox.md)

## Delivery notes

- Affected areas: scheduler startup, outbox worker, reconciliation, late-delivery policy, channel
  delivery, Store implementations, and failure-injection tests.
- Rollout: run reconciliation in report-only mode in staging, verify drift, then enable repairs.
- Rollback: pause delivery workers while keeping authoritative Reminder and outbox data intact.

## Comments

### 2026-08-31 — Claimed

Implementation started after issue 10 closed. The first pass will compare authoritative Reminder
rows, scheduler jobs, and outbox claim/retry behavior before adding reconciliation and late-delivery
failure injection.

### 2026-08-31 — Completed

Startup and the minute-level reconciliation job now rebuild APScheduler from authoritative owned
Reminder rows, repair wrong times, remove inverse drift, reset interrupted sends, and enforce the
15-minute missed policy while leaving Tasks pending. Recently delayed occurrences are atomically
claimed and grouped into one participant summary. Existing outbox claims were verified through
five bounded failures into a visible poison state. The protected smoke harness was reviewed and
updated for the owned Store signature and UTC scheduling boundary. Two smoke reproductions, 189
Python tests, Ruff, dashboard lint/build, and diff checks passed.
