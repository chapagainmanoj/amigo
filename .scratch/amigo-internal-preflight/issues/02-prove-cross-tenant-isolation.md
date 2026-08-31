# Prove Cross-Tenant Isolation

Status: closed
Label: `ready-for-human`
Severity: `severity:critical`
Type: HITL
Owner: unassigned

## What to build

Establish end-to-end tenant isolation for the invitation-beta data model. Every browser policy,
backend Store mutation, and service-role operation must resolve the authenticated actor and reject
cross-participant access with the same safe outcome as a missing resource.

The existing Task-status ownership predicate is partial evidence; this slice completes Reminder
ownership and the full two-participant integration matrix. Independent security review is
required.

## Acceptance criteria

- [x] Participant A cannot select or mutate Participant B's Profile, Tasks, Reminders, Sessions,
  Messages, feedback, usage events, or Pairing data using guessed identifiers.
- [x] Every Task and Reminder mutation includes an authenticated `user_id` ownership predicate in
  all Store implementations.
- [x] Service-role functions enforce explicit actor/row ownership and are unavailable to anonymous
  and authenticated client roles.
- [x] Missing-resource and wrong-owner requests return the same safe response and create no side
  effect or information leak.
- [x] Two-participant security integration tests run against an isolated Supabase environment and
  record reviewed evidence.

## Blocked by

- [Secure Single-Use Pairing Tokens](01-secure-single-use-pairing-tokens.md)

## Delivery notes

- Affected areas: RLS policies, Store ownership predicates, authenticated API operations, test
  fakes, and Supabase security integration tests.
- Rollout: verify against isolated data, then staging, before any external participant exists.
- Rollback: disable affected mutations or access paths; never restore a policy known to permit
  cross-tenant access.

## Comments

### 2026-08-30 — Claimed

Implementation started. Store and test changes may proceed; any production RLS/grant migration
will be presented for explicit human review before it is added under `migrations/`.

### 2026-08-30 — Policy review requested

- Reminder creation, reads, updates, scheduler claims, and callback mutations now carry an owned
  `user_id` through MemoryStore, InMemoryStore, and FakeStore.
- Reminder updates reject ownership/identity-field rewrites, and Reminder creation verifies the
  referenced Task has the same owner.
- An isolated PostgreSQL probe with Supabase-style roles confirmed current row reads are isolated,
  but reproduced cross-tenant Task-to-Session and Reminder-to-Task references under the broad
  policies in migration 002.
- The exact replacement grants and RLS policies are available at
  [Review: Tenant Isolation Policies Migration 004](../reviews/004-tenant-isolation-policies.md).
- Verification before migration: 13 focused ownership tests and all 96 backend tests pass; Ruff
  and `git diff --check` pass.

### 2026-08-30 — Completed

- The project owner approved the exact Migration 004 proposal before it was added as
  `migrations/004_tenant_isolation_policies.sql`; the applied file matches the approved SQL.
- A fresh PostgreSQL 15 database applied migrations 001 through 004 successfully with a
  Supabase-compatible `anon`, `authenticated`, `service_role`, and `auth.uid()` environment.
- The two-participant SQL matrix proved row-read isolation; denied anonymous, feedback, usage, and
  Pairing access; blocked cross-tenant Task and Reminder mutations and relationship rewrites; and
  preserved permitted same-owner browser operations and service-role Pairing RPC access.
- CI now applies all migrations and runs the SQL isolation matrix on PostgreSQL 15 before lint and
  unit tests.
- Application verification passed: 13 focused Store ownership tests, all 96 backend tests, Ruff,
  and `git diff --check`.
