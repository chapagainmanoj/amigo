# Complete the Dashboard-First Activation Journey

Status: open
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: unassigned

## What to build

Deliver the approved resumable Activation Journey from a verified Dashboard Account through
Pairing, profile setup, a confirmed private test Task and Reminder, Telegram delivery and
resolution, and automatic reflection of Activation on the dashboard.

Human review is required for journey persistence and the high-risk Pairing handoff.

## Acceptance criteria

- [ ] A verified Dashboard Account acknowledges the narrow promise, beta limits, and privacy/terms
  before receiving an expiring Pairing deep link or QR code.
- [ ] Successful Pairing is detected automatically by the open dashboard; Telegram confirms the
  linked Dashboard Account without exposing identifiers and provides a return path.
- [ ] The participant sets a validated preferred name, explicit IANA timezone, and beta quiet
  hours without a hardcoded geographic assumption or Pairing dead end.
- [ ] The journey creates one clearly labelled private test Task, confirms a Reminder two minutes
  ahead, and requires actual Telegram delivery plus Done, Skip, or Later resolution.
- [ ] Activation completes only when the resolution is reflected in the canonical dashboard
  snapshot; scheduling, timeout, or an error cannot mark it complete.
- [ ] Versioned progress resumes at the first incomplete step and provides specific recovery for
  email verification, token expiry/replacement/use, closed-dashboard return, and failed or late
  delivery.

## Blocked by

- [Secure Single-Use Pairing Tokens](01-secure-single-use-pairing-tokens.md)
- [Serve One Consistent Dashboard Snapshot](10-serve-consistent-dashboard-snapshot.md)
- [Clarify and Confirm Reminder Time](08-clarify-and-confirm-reminder-time.md)

## Delivery notes

- Affected areas: authenticated dashboard onboarding, Pairing handoff, Telegram onboarding,
  profile/quiet-hour setup, test Task/Reminder, Activation state, and browser/integration tests.
- Rollout: exercise with clean staging accounts across desktop and mobile before enabling normal
  dashboard access.
- Rollback: return incomplete participants to the first safe resumable step; never synthesize
  Activation or retain an unsafe active token.

## Comments

