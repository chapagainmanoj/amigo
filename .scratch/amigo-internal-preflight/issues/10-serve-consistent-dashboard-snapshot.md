# Serve One Consistent Dashboard Snapshot

Status: open
Label: `in-progress`
Severity: `severity:high`
Type: HITL
Owner: Codex

## What to build

Replace independent browser reads with one authenticated, tenant-scoped, versioned dashboard
snapshot. Tasks, daily progress, Inbox, Carried over Tasks, Reminders, and recent Sessions are
assembled consistently server-side and replaced atomically in the client.

This slice requires review of any database view or transactional snapshot function.

## Acceptance criteria

- [ ] One authenticated endpoint returns snapshot version, generation time, current IANA timezone,
  local Planning Day, task populations, progress, Reminders, and customer-readable Sessions.
- [ ] Today's Task list and progress use exactly the same due-date and lifecycle population; Inbox
  and Carried over Tasks are separate and excluded from today's denominator.
- [ ] Every displayed Reminder resolves to an owned Task or explicitly explains its carried-over
  state, and “no tasks pending” cannot contradict a pending Reminder.
- [ ] Reminder presentation includes date, localized time, timezone, and overdue/delivery state.
- [ ] Mutations and realtime invalidations trigger a fresh snapshot; the browser never merges
  direct table payloads or mixed snapshot versions.
- [ ] Cross-midnight, legacy Task, stale Session, and previously contradictory `0 of 0` states have
  integration coverage.

## Blocked by

- [Capture an Inbox Task Through One Shared Command](04-capture-inbox-task-through-shared-command.md)
- [Schedule a Reminder Through the Durable Outbox](05-schedule-reminder-through-durable-outbox.md)
- [Resolve a Task and Reminder Consistently](06-resolve-task-and-reminder-consistently.md)
- [Apply Later Consistently Across Both Surfaces](07-apply-later-across-surfaces.md)

## Delivery notes

- Affected areas: dashboard read model, authenticated API, Store query contract, Session
  presentation, frontend state replacement, and browser/integration tests.
- Rollout: compare legacy and canonical snapshots in staging, then remove direct product-table
  reads and writes from the browser.
- Rollback: return to the last server-derived snapshot version; do not restore independent browser
  mutations.

## Comments

### 2026-08-31 — Claimed

Implementation started after issue 09 closed. The first pass will audit existing dashboard reads,
API ownership boundaries, Task populations, Reminder presentation, and Session reconciliation
before determining whether a protected snapshot function or view is required.
