# Clarify and Confirm Reminder Time

Status: closed
Label: `done`
Severity: `severity:high`
Type: AFK
Owner: unassigned

## What to build

Resolve Reminder time as an explicit local date, wall time, IANA timezone, UTC instant, confidence,
and clarification requirement. The participant sees and confirms the exact interpretation before
persistence; ambiguous or invalid expressions cannot silently schedule a Reminder.

## Acceptance criteria

- [x] Bare hours, dates without times, fuzzy periods, contradictory inputs, and already-passed
  same-day times require clarification or explicit confirmation before mutation.
- [x] Unambiguous relative expressions may schedule directly but still return the exact local date,
  time, and timezone.
- [x] Nonexistent DST wall times require another choice; repeated wall times use the approved
  earlier occurrence unless the participant selects otherwise.
- [x] Automatic suggestions avoid quiet hours, explicit quiet-hour requests require one-time
  confirmation, and saved Reminders remain anchored to their confirmed UTC instant.
- [x] Tests cover half-hour timezones, both UTC-offset directions, DST transitions, midnight, and
  ambiguous local hours.

## Blocked by

- [Schedule a Reminder Through the Durable Outbox](05-schedule-reminder-through-durable-outbox.md)

## Delivery notes

- Affected areas: deterministic time resolution, agent Tool contract, confirmation conversation,
  Reminder persistence, display formatting, and evaluation fixtures.
- Rollout: compare new resolution outcomes against the current parser in staging without
  persisting ambiguous results.
- Rollback: disable automatic scheduling for affected expressions and fall back to clarification.

## Comments

### 2026-08-31 — Claimed

Implementation started after issue 07 closed. The current HH:MM parser path will be replaced by a
typed resolution result and explicit confirmation boundary, with invalid and ambiguous wall times
blocked before any Reminder command executes.

### 2026-08-31 — Completed

Added typed full-instant resolution and an exact-label confirmation boundary before Reminder
persistence. Relative expressions remain direct when unambiguous; invalid DST gaps, bare/fuzzy or
contradictory input, passed wall times, and unconfirmed quiet-hour requests cannot mutate state.
Repeated DST hours default to the earlier occurrence with an explicit later-fold option, and
automatic suggestions move to wake time. Verified with 177 Python tests, Ruff, dashboard lint and
build, and `git diff --check`.
