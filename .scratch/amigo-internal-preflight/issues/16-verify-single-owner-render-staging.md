# Verify the Single-Owner Render Staging Path

Status: open
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: unassigned

## What to build

Establish and verify the Internal Preflight deployment path on Render with exactly one active
Telegram webhook and scheduler owner. The staging release must remain continuously capable of
scheduling, recover after restart, expose readiness and Reminder evidence, and complete the
dashboard-to-Telegram Core Loop.

This slice requires human access to deployment and provider configuration.

## Acceptance criteria

- [ ] Render is the only active beta-intended webhook/scheduler platform and Fly configuration is
  clearly inactive so it cannot become a competing owner accidentally.
- [ ] Staging uses separate Telegram, Supabase, dashboard, and model resources and passes
  fail-closed startup and schema-version checks.
- [ ] Exactly one scheduler owner and webhook destination are verified before and after a
  deployment restart.
- [ ] Restart recovery restores scheduled Reminder work without duplicate, cross-participant, or
  lost delivery.
- [ ] Liveness, readiness, application errors, Reminder delivery, and lateness are observable for
  the tested release.
- [ ] A synthetic clean account completes Dashboard Account → Pairing → Task → Reminder → Done →
  dashboard synchronization in staging.

## Blocked by

- [Fail Closed Under Unsafe Production Configuration](03-fail-closed-production-configuration.md)
- [Expose Reminder Delivery, Lateness, and Readiness](12-expose-reminder-delivery-lateness-and-readiness.md)
- [Remove Blocking Supabase Access From the Event Loop](13-remove-blocking-supabase-access.md)
- [Complete the Dashboard-First Activation Journey](15-complete-dashboard-first-activation.md)

## Delivery notes

- Affected areas: Render services, staging provider resources, webhook ownership, scheduler
  process, readiness, deployment checks, and synthetic Core Loop automation.
- Rollout: verify staging first; promotion remains manual and no external invitation is authorized
  by this issue.
- Rollback: restore the last known-good single-owner release and webhook destination using the
  documented deployment rollback.

## Comments

