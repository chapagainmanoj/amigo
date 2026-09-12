# Remove Blocking Supabase Access From the Event Loop

Status: open
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: Codex

## What to build

Move Store and authentication network access to the Supabase SDK's native asynchronous client so
concurrent Turns and due Reminder work do not block the application event loop. Preserve Store
boundaries, ownership behavior, and a bounded fallback only for specifically incompatible SDK
operations.

This slice requires human review of protected Supabase singleton wiring.

## Acceptance criteria

- [x] No synchronous Supabase network call executes directly on the application event loop in
  Store, authentication, Pairing, dashboard, outbox, or reconciliation paths.
- [x] Database access remains behind MemoryStore and any interface changes are mirrored in
  InMemoryStore and FakeStore.
- [x] A worker-thread fallback, if unavoidable, is bounded, documented per operation, observable,
  and covered by a removal follow-up.
- [ ] Event-loop delay and database latency are measured before and after the change under
  concurrent Turn and due-Reminder staging traffic.
- [x] Ownership, error mapping, transaction, outbox, and retry behavior remain unchanged under
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

### 2026-08-31 — Claimed

Implementation started after issue 12 closed. The first pass will inventory every Supabase SDK
call, current client construction, authentication access, and SDK async support before proposing
the protected singleton-wiring change for human review.

### 2026-08-31 — Async singleton proposed for review

The installed Supabase 2.31 SDK exposes native `AsyncClient`/`acreate_client`, and PostgREST async
query builders provide awaitable `execute()` methods. The proposal replaces the synchronous
singleton in protected `src/db/supabase.py` with a lazily initialized async singleton guarded by
an async lock. No worker-thread fallback is required.

After approval, `MemoryStore` will connect during FastAPI lifespan startup, all Store/Auth SDK
operations will await the native async client, and concurrency tests will measure event-loop delay
and database-operation latency while preserving RPC parameters, ownership filters, and error
mapping. The protected file has not been changed yet.

### 2026-08-31 — Local implementation complete; staging evidence required

The approved async singleton is in place. FastAPI initializes `MemoryStore` during lifespan,
Store and Auth use native awaitable SDK operations, and all Store methods emit content-free
operation/outcome/duration logs. `connect()` is mirrored by `InMemoryStore` and `FakeStore`; no
thread fallback exists.

Static regression coverage verifies every Store `execute()` and Auth `get_user()` call remains
awaited. A deterministic 20-operation concurrency test proves all database operations can overlap
while a separate event-loop task advances. Ownership filters, Pairing error mapping, Reminder
delivery, outbox, scheduler recovery, and transaction RPC tests remain green.

The repository cannot truthfully satisfy the remaining before/after staging criterion locally:
the documented pre-change staging event-loop and database-latency baseline was never captured,
and no authorized staging workload/test identities are available in this task. Store duration
logs and the concurrency regression make the post-change measurement possible, but the
representative Turn/due-Reminder run must be completed against staging before this issue closes.

Local verification passed with 199 backend tests, Ruff, scheduler smoke, dashboard lint/build,
and `git diff --check`. The protected singleton file byte-matches the human-reviewed proposal.

### 2026-08-31 — Staging measurement path prepared

The application now emits one-second content-free event-loop-delay samples in addition to Store
operation latency. `scripts/summarize_runtime_evidence.py` calculates nearest-rank p50/p95/max and
error counts from only those fields. `docs/staging-performance-evidence.md` fixes the two-revision,
three-trial workload, metadata, safety boundary, thresholds, and evidence artifacts required for
the missing staging comparison. Local verification is now 202 backend tests; it still does not
substitute for executing that procedure on dedicated staging resources.

### 2026-08-31 — Staging resource audit

A read-only repository and Render-dashboard audit found no dedicated staging service or test
identity. `render.yaml` defines only the production Amigo service, and the only available Render
browser session is signed out. The production service is not an acceptable target for the
synthetic multi-participant failure/replay workload.

Independent review found no remaining local implementation or standards defects and reproduced
the 202-test, Ruff, scheduler-smoke, and diff checks. It also confirmed that this issue cannot
close truthfully until either dedicated staging access plus test identities are supplied, or a
human-approved tracker change moves the before/after staging measurement to the staging-gate
issue and resolves the dependency cycle with issue 16.

### 2026-09-01 — Protected singleton approved and reverified

The human-approved `src/db/supabase.py` update is retained exactly as the reviewed native-async
singleton: lazy `AsyncClient` construction is guarded by one async lock, concurrent callers share
one client, and no worker-thread fallback was introduced. After correcting a date-dependent Later
test fixture uncovered during independent review, local verification passed with 213 backend tests,
Ruff, the 60-case/3-repetition Gate A schema validation, scheduler smoke, dashboard lint/build, and
`git diff --check`. The issue remains open only for its explicit before/after staging measurement.

### 2026-09-12 — Re-audited; still open only on staging measurement

Re-checked against the current worktree. Four of the five acceptance criteria remain satisfied by
the checked-in native-async Supabase access, the store-layer boundary, and the regression and
failure-injection tests; 258 backend tests and Ruff pass.

The open criterion is unchanged and is not a code gap: event-loop delay and database latency must
be measured before and after the change under concurrent Turn and due-Reminder traffic in staging.
Producing it needs a non-production Render service, a separate staging Supabase project, and a
dedicated Telegram bot. No local substitute is recorded as satisfying this criterion.
