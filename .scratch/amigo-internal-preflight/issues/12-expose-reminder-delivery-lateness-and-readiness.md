# Expose Reminder Delivery, Lateness, and Readiness

Status: closed
Label: `done`
Severity: `severity:high`
Type: HITL
Owner: Codex

## What to build

Create operator-visible evidence for Reminder acceptance and timing. Record the approved immutable
occurrence and attempt timestamps, expose scheduler/outbox health, and make readiness fail when a
required dependency or scheduler heartbeat cannot support the Core Loop.

This slice requires review of the reliability-instrumentation migration.

## Acceptance criteria

- [x] Eligible Reminder occurrences record confirmation, scheduled, first-claim,
  provider-acceptance, terminal, acknowledgement, and cancellation timestamps without rewriting
  history.
- [x] An immutable attempt ledger records timing, normalized result/cause, idempotency key, and
  retry decision; uninstrumented historical rows are marked unmeasurable.
- [x] Reminder Lateness, Scheduler Lag, Provider Latency, outbox lag, oldest effect, failed effects,
  and reconciliation drift are observable without message content.
- [x] Liveness and readiness are distinct, and readiness fails for an unavailable required
  dependency or missing scheduler heartbeat.
- [x] An intentionally injected Reminder failure is visible to the operator with its occurrence
  and attempt outcome.
- [x] Staging and production synthetic results remain distinguishable from participant Reminder
  evidence.

## Blocked by

- [Recover Reminder Scheduling After Restart](11-recover-reminder-scheduling-after-restart.md)

## Delivery notes

- Affected areas: Reminder reliability schema, channel acceptance recording, scheduler heartbeat,
  health/readiness endpoints, metrics, alerts, and synthetic checks.
- Rollout: instrument staging first, validate timestamp completeness, and only then use metrics as
  release evidence.
- Rollback: disable faulty reporting while retaining immutable occurrence/attempt data; readiness
  must remain conservative.

## Comments

### 2026-08-31 — Claimed

Implementation started after issue 11 closed. The first pass will map Reminder occurrence and
attempt timestamps, scheduler/outbox health sources, dependency checks, and the current liveness
endpoint before proposing the protected reliability-instrumentation migration.

### 2026-08-31 — Migration 011 proposed for review

The proposed migration adds immutable Reminder occurrence and delivery-attempt evidence,
participant/staging-synthetic/production-synthetic classification, scheduler heartbeat and
reconciliation drift state, atomic delivery claim/finalization functions, and content-free
reliability health metrics. Historical Reminders are explicitly backfilled as
`pre_instrumentation` and unmeasurable.

The complete 001–011 sequence passed on a clean PostgreSQL 15 database, including assertions for
legacy backfill, accepted delivery, injected provider failure, synthetic separation, occurrence
and attempt immutability, heartbeat/readiness inputs, timing metrics, and denial of authenticated
client access. The protected migration file will not be created until human approval.

### 2026-08-31 — Closed

Human-approved migration 011 was added exactly as reviewed. Reminder sends now atomically create
and finish immutable attempts, reconciliation records heartbeat and drift, and ambiguous provider
or interrupted-delivery outcomes remain terminal rather than being retried into a duplicate.
`/health` remains liveness-only while `/ready` fails on database-check failure, stale scheduler
heartbeat, or failed durable effects.

Verification passed: the exact PostgreSQL 15 CI sequence through migration 011 (including legacy
backfill, accepted and injected-failure evidence, synthetic separation, immutability, and client
permission denial), 194 backend tests, Ruff, scheduler smoke, dashboard lint/build, and
`git diff --check`.
