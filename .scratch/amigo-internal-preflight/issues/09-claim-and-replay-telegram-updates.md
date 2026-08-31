# Claim and Replay Telegram Updates Safely

Status: closed
Label: `done`
Severity: `severity:high`
Type: HITL
Owner: unassigned

## What to build

Persist an atomic claim for each Telegram update before processing and serialize active Turns per
participant. Duplicate delivery, concurrent replay, or process retry must converge on one Turn and
one set of Task/Reminder effects without silently losing failed internal work.

This slice requires review of the update-claim persistence migration.

## Acceptance criteria

- [x] The same Telegram `update_id` can be claimed successfully only once, including under
  concurrent requests.
- [x] A duplicate receives a safe Telegram acknowledgement while the original result and failure
  state remain inspectable.
- [x] Tool and command idempotency prevents replayed Task creation, Reminder scheduling,
  resolution, and Later effects.
- [x] Two rapid messages from one participant execute in deterministic order while different
  participants may proceed within configured concurrency limits.
- [x] Deduplication permits legitimate repeated Tasks on different Planning Days.

## Blocked by

- [Resolve a Task and Reminder Consistently](06-resolve-task-and-reminder-consistently.md)
- [Apply Later Consistently Across Both Surfaces](07-apply-later-across-surfaces.md)

## Delivery notes

- Affected areas: Telegram webhook ingestion, update claims, per-participant Turn serialization,
  command idempotency keys, operational logging, and concurrency tests.
- Rollout: replay captured non-sensitive fixtures and concurrent duplicates in staging before
  enabling the claim path in production.
- Rollback: stop webhook intake or revert to the last claim implementation without deleting claim
  history.

## Comments

### 2026-08-31 — Claimed

Implementation started after issue 08 closed. First pass will map webhook acknowledgement,
per-participant Turn execution, and existing command idempotency boundaries before proposing the
protected update-claim migration for review.

### 2026-08-31 — Completed

Migration 009 was reviewed and approved, then added unchanged. The webhook atomically claims each
supported Telegram update before handler execution, acknowledges duplicates, and records a
content-free completed or failed outcome. Stable update-derived Turn IDs connect replay protection
to the existing Task/Reminder command receipts. Participant locks preserve same-user arrival order
without blocking different users. The exact PostgreSQL 15 CI sequence through migration 009 and
all SQL regressions passed; Python, lint, web, and diff verification are recorded at closure.
