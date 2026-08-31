# Fail Closed Under Unsafe Production Configuration

Status: closed
Label: `ready-for-human`
Severity: `severity:critical`
Type: HITL
Owner: unassigned

## What to build

Prevent Amigo from starting in production when its identity, webhook, database, model, dashboard
origin, or invitation-access controls are absent or unsafe. Development and test defaults remain
convenient, but production behavior is explicit and closed by default.

This slice requires human review before protected configuration defaults are changed.

## Acceptance criteria

- [x] Production startup fails for an empty or unsafe Telegram token, webhook secret, Supabase URL
  or service credential, model credential, dashboard origin, or access mode.
- [x] Production supports an explicit closed or invitation-controlled access posture; an empty
  allowlist cannot accidentally mean public access.
- [x] Failure messages identify the invalid setting without logging its secret value.
- [x] Development, tests, and CLI mode retain documented minimal configuration without weakening
  production validation.
- [x] Automated configuration tests cover every fail-closed condition and a valid production
  configuration.

## Blocked by

None - can start immediately.

## Delivery notes

- Affected areas: application settings, startup validation, access checks, deployment environment
  documentation, and configuration tests.
- Rollout: validate in CI and staging with deliberately missing values before production.
- Rollback: stop deployment and restore the last configuration validator known to reject unsafe
  production startup.

## Comments

### 2026-08-30 — Claimed

Implementation started with an audit of startup validation, webhook initialization, dashboard
origin handling, and Telegram access control. Changes to protected `src/config.py` will be
presented for explicit human review before editing that file.

### 2026-08-30 — Configuration review requested

- Production currently accepts the development-open empty allowlist, Telegram callbacks bypass
  the allowlist, and webhook initialization failures are logged but do not abort startup.
- The proposed typed `ACCESS_MODE` and `DASHBOARD_URL` additions, plus the surrounding fail-closed
  behavior, are documented in
  [Review: Production Configuration Settings](../reviews/production-configuration-settings.md).
- Implementation is paused before editing protected `src/config.py`.

### 2026-08-30 — Completed

- The project owner approved the exact protected Settings change before `src/config.py` was
  edited; the resulting diff matches the approved proposal.
- Production validation now runs before Telegram, Supabase, scheduler, or webhook wiring and
  identifies invalid setting names without including their values.
- Production requires public HTTPS application, dashboard, and Supabase origins; safe Telegram,
  Supabase, and model credentials; and an explicit `closed`, `allowlist`, or `invite` posture.
- `closed` denies messages, callbacks, and new Pairing links; `allowlist` fails closed on empty or
  malformed IDs; and `invite` admits Pairing deep links plus already-paired profiles.
- Callback access checks now match message access checks, production webhook initialization
  failures abort startup, and production CORS exposes only the configured dashboard origin.
- Deployment and environment documentation now includes `ACCESS_MODE` and `DASHBOARD_URL`.
- Verification passed with 121 Python tests, Ruff, `git diff --check`, a valid closed-production
  import, and an expected setting-only startup failure for `ACCESS_MODE=open`.
