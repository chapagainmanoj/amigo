# Secure Single-Use Pairing Tokens

Status: closed
Label: `ready-for-human`
Severity: `severity:critical`
Type: HITL
Owner: unassigned

## What to build

Make Pairing tokens a backend-only, expiring, single-use capability. A Dashboard Account can
generate a token and complete Pairing without exposing token rows to browser database roles;
replacement, expiry, replay, and already-linked states have deterministic safe outcomes.

This slice requires human review of the production-affecting migration and Pairing security.

## Acceptance criteria

- [x] Anonymous and authenticated database clients cannot select, insert, update, or delete
  Pairing-token rows; only the service-role backend path can use them.
- [x] Tokens are generated with bounded lifetime and entropy, consumed atomically once, and an
  expired, used, or malformed token cannot complete Pairing.
- [x] Generating a replacement invalidates older unconsumed tokens for the same Dashboard Account,
  and generation is rate-limited.
- [x] Existing Dashboard Account and Telegram Profile links cannot be silently reassigned or
  duplicated through token replay.
- [x] The reviewed migration succeeds from both an empty database and the previous schema, with
  automated Pairing lifecycle coverage.

## Blocked by

None - can start immediately.

## Delivery notes

- Affected areas: Pairing persistence, grants/RLS, authenticated token generation, Telegram deep
  link consumption, and Pairing tests.
- Rollout: apply and verify in an isolated Supabase environment before staging.
- Rollback: disable token generation/consumption first; use a reviewed database rollback or
  forward-fix without reopening client access.

## Comments

### 2026-08-30 — Claimed

Implementation started. Application and test changes may proceed, but production migration changes
remain paused for the required human review.

### 2026-08-30 — Migration review requested

Application behavior and Store parity are implemented with 16 focused Pairing tests and 84 passing
tests overall. The exact proposed production migration is available at
[Review: Secure Pairing Tokens Migration 003](../reviews/003-secure-pairing-tokens.md). Implementation
is paused before creating the protected migration file.

### 2026-08-30 — Completed

- Human review approved the exact migration proposal before it was added as
  `migrations/003_secure_pairing_tokens.sql`; the applied file matches the approved SQL exactly.
- PostgreSQL 15 clean-schema validation applied migrations 001, 002, and 003 successfully.
- PostgreSQL 15 previous-schema validation applied 003 after representative existing consumed and
  unconsumed Pairing-token rows without losing them.
- Live SQL assertions passed for RLS enablement; revoked anonymous/authenticated table and RPC
  access; service-role grants; replacement invalidation; five-per-15-minute rate limiting; replay;
  idempotent existing links; identity-conflict rejection; and reusable intended token after a
  conflicting attempt.
- Python verification: 16 focused Pairing tests passed, all 84 backend tests passed, Ruff passed,
  and `git diff --check` passed.
