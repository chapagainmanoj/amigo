# Expose Reminder Delivery, Lateness, and Readiness

Status: open
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: unassigned

## What to build

Create operator-visible evidence for Reminder acceptance and timing. Record the approved immutable
occurrence and attempt timestamps, expose scheduler/outbox health, and make readiness fail when a
required dependency or scheduler heartbeat cannot support the Core Loop.

This slice requires review of the reliability-instrumentation migration.

## Acceptance criteria

- [ ] Eligible Reminder occurrences record confirmation, scheduled, first-claim,
  provider-acceptance, terminal, acknowledgement, and cancellation timestamps without rewriting
  history.
- [ ] An immutable attempt ledger records timing, normalized result/cause, idempotency key, and
  retry decision; uninstrumented historical rows are marked unmeasurable.
- [ ] Reminder Lateness, Scheduler Lag, Provider Latency, outbox lag, oldest effect, failed effects,
  and reconciliation drift are observable without message content.
- [ ] Liveness and readiness are distinct, and readiness fails for an unavailable required
  dependency or missing scheduler heartbeat.
- [ ] An intentionally injected Reminder failure is visible to the operator with its occurrence
  and attempt outcome.
- [ ] Staging and production synthetic results remain distinguishable from participant Reminder
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

