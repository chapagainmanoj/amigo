# Remove Blocking Supabase Access From the Event Loop

Status: open
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: unassigned

## What to build

Move Store and authentication network access to the Supabase SDK's native asynchronous client so
concurrent Turns and due Reminder work do not block the application event loop. Preserve Store
boundaries, ownership behavior, and a bounded fallback only for specifically incompatible SDK
operations.

This slice requires human review of protected Supabase singleton wiring.

## Acceptance criteria

- [ ] No synchronous Supabase network call executes directly on the application event loop in
  Store, authentication, Pairing, dashboard, outbox, or reconciliation paths.
- [ ] Database access remains behind MemoryStore and any interface changes are mirrored in
  InMemoryStore and FakeStore.
- [ ] A worker-thread fallback, if unavoidable, is bounded, documented per operation, observable,
  and covered by a removal follow-up.
- [ ] Event-loop delay and database latency are measured before and after the change under
  concurrent Turn and due-Reminder staging traffic.
- [ ] Ownership, error mapping, transaction, outbox, and retry behavior remain unchanged under
  regression and failure-injection tests.

## Blocked by

- [Serve One Consistent Dashboard Snapshot](10-serve-consistent-dashboard-snapshot.md)
- [Recover Reminder Scheduling After Restart](11-recover-reminder-scheduling-after-restart.md)

## Delivery notes

- Affected areas: Supabase client construction, Store/authentication calls, dependency injection,
  concurrency instrumentation, fakes, and regression tests.
- Rollout: establish a staging baseline, switch one owned path at a time, then rerun Core Loop and
  scheduler recovery tests.
- Rollback: restore the last correct client path with bounded isolation; never hide event-loop
  blocking by removing measurements.

## Comments

