# Capture an Inbox Task Through One Shared Command

Status: closed
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: unassigned

## What to build

Create the first canonical cross-surface mutation: Telegram and dashboard adapters submit an
authenticated Create Task command to the same domain operation. A commitment without a Planning
Day becomes one pending Inbox Task, and command replay returns the stored result rather than
creating a duplicate.

This slice introduces the reviewed lifecycle and command-receipt database foundation.

## Acceptance criteria

- [x] Telegram and dashboard Task creation use the same authenticated application command and
  neither accepts a client-supplied participant identity.
- [x] A Task without a Planning Day is stored as `pending` with no `due_date` and appears in Inbox;
  audit timestamps do not place it in today's population.
- [x] Canonical Task states are `pending`, `completed`, `skipped`, and `cancelled`; legacy
  `deferred` behavior is not produced by the new path.
- [x] A matching idempotency-key replay returns the stored canonical result, while key reuse with
  different input fails without mutation.
- [x] Store behavior and automated tests remain equivalent across MemoryStore, InMemoryStore, and
  FakeStore.

## Blocked by

- [Prove Cross-Tenant Isolation](02-prove-cross-tenant-isolation.md)

## Delivery notes

- Affected areas: Task lifecycle schema, command receipts, authenticated commands, Tools, Store
  implementations, dashboard mutation adapter, and tests.
- Rollout: migrate and exercise the new path in staging while legacy reads remain compatible.
- Rollback: disable the new adapters and preserve created Tasks; use a reviewed forward migration
  for any schema correction.

## Comments

### 2026-08-30 — Claimed

Implementation started from the approved Task lifecycle and cross-surface state decisions. The
shared application command and Store parity will be built first; the transactional database
function and canonical lifecycle migration will be presented for explicit review before adding a
protected migration file.

### 2026-08-30 — Migration review requested

- Telegram and dashboard now use one `CreateTaskCommand`; both adapters inject the authenticated
  actor and neither accepts `user_id` as Task input.
- FakeStore and InMemoryStore prove Inbox semantics, Planning Day population, exact replay,
  payload conflict rejection, and cross-tenant Session rejection.
- The dashboard creates Tasks through `POST /api/tasks` and renders unscheduled Tasks in Inbox.
- Application code now produces only canonical Task states; new Tasks without a Planning Day do
  not enter the today population even though audit dates remain populated.
- The exact transactional schema/function proposal is available at
  [Review: Canonical Task Command Migration 005](../reviews/005-canonical-task-command.md).
- Pre-migration verification: all 132 Python tests, Ruff, dashboard lint/build, and
  `git diff --check` pass.
- The proposed SQL was also pre-validated on PostgreSQL 15 from a clean schema and from a
  representative previous schema containing legacy `done`, `deferred`, and `skipped` rows.
  Live assertions passed for replay, conflict-without-mutation, tenant-owned Session references,
  client privilege revocation, service-only RPC access, Inbox semantics, and canonical backfill.

### 2026-08-30 — Completed

- The project owner approved the exact Migration 005 proposal before it was added as
  `migrations/005_canonical_task_command.sql`; the migration file matches the approved SQL.
- CI now seeds representative legacy Task states, applies Migration 005, proves canonical
  backfill, runs the full tenant-isolation matrix, and exercises the live Create Task RPC.
- PostgreSQL 15 final validation passed the exact CI sequence, including exact replay,
  conflict-without-mutation, owned Session enforcement, client privilege revocation, and
  service-role command access.
- Telegram and dashboard adapters inject the actor into the same command. The dashboard request
  schema rejects client-supplied identity and renders no-Planning-Day Tasks in Inbox.
- Verification passed with 132 Python tests, Ruff, dashboard lint/build, and `git diff --check`.
