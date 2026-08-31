# Recover Reminder Scheduling After Restart

Status: open
Label: `ready-for-agent`
Severity: `severity:high`
Type: AFK
Owner: unassigned

## What to build

Treat the database as Reminder authority and APScheduler as a rebuildable projection. Startup,
outbox replay, and periodic reconciliation restore missing or wrongly timed jobs and remove jobs
that no longer correspond to an active owned Reminder.

## Acceptance criteria

- [ ] Startup reconstructs exactly one stable scheduler job for every canonical Reminder that
  requires future delivery.
- [ ] Reconciliation repairs missing or wrongly timed jobs and cancels jobs for missing, terminal,
  or wrong-owner Reminders.
- [ ] Outbox effects use atomic claims, bounded retries, stable identities, and a visible poison
  state rather than disappearing after repeated failure.
- [ ] A Reminder no more than 15 minutes late is delivered at most once with delayed timing;
  anything older becomes missed while its Task remains pending.
- [ ] Recovery emits at most one summary rather than a burst of stale Reminder messages.
- [ ] Restart, interrupted outbox processing, scheduler outage, duplicate effect, and inverse-drift
  cases converge under automated failure injection.

## Blocked by

- [Schedule a Reminder Through the Durable Outbox](05-schedule-reminder-through-durable-outbox.md)

## Delivery notes

- Affected areas: scheduler startup, outbox worker, reconciliation, late-delivery policy, channel
  delivery, Store implementations, and failure-injection tests.
- Rollout: run reconciliation in report-only mode in staging, verify drift, then enable repairs.
- Rollback: pause delivery workers while keeping authoritative Reminder and outbox data intact.

## Comments

