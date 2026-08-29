# Resolve the Task and Reminder Lifecycle

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:grilling`
Type: HITL / grilling
Severity: `severity:high`
Owner: unassigned
Blocked by: none

## Question

What are the canonical semantics for Task dates, ambiguous times, quiet hours, Snooze, Defer,
missed or overdue Reminders, cross-midnight carry-over, and terminal Task resolution?

## Comments

### Resolution — 2026-08-29

Adopt the following canonical lifecycle contract.

#### Task dates and Inbox

- `created_at` is immutable audit history. It never decides which planning day contains a Task.
- `due_date` is the user's intended planning day, interpreted in their current IANA timezone.
- A Reminder stores the exact delivery instant in UTC while preserving the intended local date,
  local time, and IANA timezone needed to explain it and handle timezone/DST changes.
- A Task may have a `due_date` without a Reminder.
- A Task receives a `due_date` when the user supplies a day or when it is captured as an answer
  during an explicit daily-planning flow. Otherwise it enters an unscheduled Inbox with no
  `due_date`; Amigo confirms it and may ask when the user wants to do it.
- Inbox Tasks do not count in daily progress and cannot receive a Reminder until the date/time is
  resolved. They offer Schedule, Move to today, Done, and Cancel actions.
- “Today,” daily progress, and carry-over use `due_date`, timezone, and lifecycle state. Existing
  `created_date` planning logic must be migrated away; the field may remain temporarily for
  compatibility but is audit metadata only.

#### Time resolution and ambiguity

- Resolution produces the full local date, time, IANA timezone, UTC instant, confidence, and a
  clarification requirement. Reducing an expression to `HH:MM` is not valid.
- Bare hours such as “at 8,” a day without a time, fuzzy periods such as “after lunch,” and a time
  that already passed today require clarification or confirmation. Amigo never silently relies on
  a parser's “prefer future” behavior.
- Unambiguous relative expressions such as “in 30 minutes” may schedule immediately.
- Before saving, Amigo confirms the resolved local date, time, and timezone in plain language.
- A nonexistent DST wall time requires another choice. For a duplicated DST wall time, use the
  earlier occurrence unless the user explicitly selects the later one.
- A saved Reminder remains anchored to its confirmed UTC instant if the profile timezone later
  changes. Display it in the user's current local timezone and offer an explicit reschedule; never
  silently move it. A Task's date remains its chosen planning-day label until explicitly moved.

#### Quiet hours

- Quiet hours use the user's configured `sleep_time` through `wake_time`, with beta defaults of
  11:00 PM through 7:30 AM local time.
- Amigo does not suggest or automatically move a Reminder into quiet hours.
- An explicit user request inside quiet hours is allowed after a one-time confirmation.
- An automatic `Later` result that enters quiet hours moves to `wake_time` and tells the user.
- Users can change or disable quiet hours. Recovery does not dump stale Reminders at wake time.

#### Later and explicit defer

- First `Later`: create a replacement Reminder for 60 minutes later.
- Second `Later`: create a replacement Reminder for 30 minutes later.
- Third `Later`: move the Task to the next local planning day and create a replacement Reminder
  at `wake_time`.
- Quiet-hour adjustment applies to every automatic delay. Every response states the exact next
  local delivery time. A user can request another explicit date/time conversationally.
- Telegram and dashboard use this one policy; the dashboard's fixed 15-minute snooze is removed.
- `Later` and defer keep the Task pending. Deferral is an event/condition and may increment a
  counter, but it is not a Task lifecycle state.

#### Late, missed, and cross-midnight behavior

- A Reminder no more than 15 minutes late may deliver exactly once, with copy that discloses the
  intended time. Record `delivery_timing=delayed` separately from lifecycle status.
- A Reminder more than 15 minutes late is not delivered; it becomes `missed` and its Task remains
  pending. The dashboard offers Reschedule, Done, and Skip.
- Recovery may send at most one missed-reminder summary rather than a burst of stale messages.
  Provider-caused failures remain distinguishable for the reliability contract in ticket 20.
- Midnight never rewrites an unfinished Task's `due_date`. A past-due pending Task has the derived
  condition `overdue` and appears under “Carried over,” outside today's completion denominator.
- Planning offers Move to today, Choose another day, Done, and Skip. Moving the date and
  rescheduling a Reminder are separate explicit operations. The third `Later` is the defined
  exception that performs both.

#### Canonical state transitions

- Task states are `pending`, `completed`, `skipped`, and `cancelled`. `completed`, `skipped`, and
  `cancelled` are terminal. `overdue` and `deferred` are derived conditions/events, not states.
- Reminder states are `pending`, `sending`, `sent`, `acknowledged`, `missed`, `failed`, and
  `cancelled`. A sent Reminder becomes acknowledged when the user acts on it.
- Done completes the Task and cancels all remaining Reminders. Skip terminates this Task
  occurrence and cancels all remaining Reminders. Cancel terminates the Task commitment.
- Later acknowledges the current Reminder, leaves the Task pending, and creates a new Reminder.
  Reschedule cancels the old Reminder and creates a new one. Terminal Reminder rows never return
  to `pending`.
- Beta permits at most one active Reminder per Task. Every transition is tenant-owned and
  idempotent, so replayed turns or repeated button taps cannot duplicate effects.

#### Consequences

- The current `created_date`-based dashboard population, `done`/`deferred` Task values, in-place
  Reminder snooze, vague “tomorrow morning” response, silent future parsing, and dashboard-only
  15-minute snooze do not conform and must be replaced.
- Schema changes require a reviewed migration and a compatibility/backfill plan. Implementation
  must preserve the Store/Tool boundaries and parity across all Store implementations.
- Tickets 06 and 09 may now prototype the cross-surface contract and define model evaluations
  against this lifecycle. Ticket 20 will define delivery eligibility, provider exclusions, and
  quantitative Reminder reliability measurement.
