# Complete the Dashboard-First Activation Journey

Status: open
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: Codex

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

### 2026-09-01 — Claimed

Implementation started after issues 01, 08, and 10 closed. The work follows the approved focused
Dashboard-first sequence and keeps normal dashboard access locked until canonical delivery and
Telegram resolution evidence exist.

### 2026-09-01 — Local implementation and protected persistence proposal under review

The local implementation now provides verified-account gating, explicit four-part beta/privacy/
rights/non-clinical acknowledgement, automatically detected single-use Pairing, profile and IANA
timezone/quiet-hour validation, an exact two-minute confirmation screen, one atomic private test
Task/Reminder/outbox command, delivery-and-resolution-based completion, polling, and specific
expired/replaced-token plus failed/late-delivery recovery. Paired incomplete Telegram users receive
a return-to-dashboard path without account identifiers instead of entering the legacy geographic
timezone guess.

Journey, command, retry, and completion behavior is mirrored in `MemoryStore`, `InMemoryStore`,
and `FakeStore`. Local verification passes with 235 backend tests, Ruff, Gate A contract
validation, scheduler smoke, dashboard lint/build, and `git diff --check`.

No protected persistence file has been added. The exact review artifacts are:

- `/tmp/amigo-migration013-proposal.sql` — SHA-256
  `e081f2165e02ae50570c718ef3c77a73a26cd25ee8799c4bb2d2ab24e8d8534b`
- `/tmp/amigo-migration013-assertions.sql` — SHA-256
  `057d055e3c447861786784dc38bda6643b46192cb957b33ec07ae5d91d0ac4d8`

A fresh PostgreSQL 15 chain through proposed migrations 012 and 013 passes acknowledgement,
Pairing denial/issuance, profile, atomic Task/Reminder/outbox/receipt, replay/conflict, failure
retry, delivery/resolution completion, cross-account non-disclosure, and role-ACL assertions.
Independent review is in progress; migration 013 still requires explicit human approval after
that review.

### 2026-09-02 — Telegram-only onboarding bypass closed

Independent review found that ordinary Telegram messages could still enter the legacy onboarding
flow and unlock normal Turns without canonical Activation evidence. The handler now processes a
Pairing deep link first, then requires both a linked Dashboard Account and a completed canonical
Activation Journey before forwarding any ordinary text to the agent. New, unlinked, old legacy,
and paired-but-incomplete profiles are directed to the verified dashboard without creating or
advancing a Telegram-only account. Activation Reminder callbacks remain available so Done, Skip,
or Later can complete the private delivery test.

Focused Telegram/Activation regressions pass with 48 tests; the complete backend suite passes with
235 tests, plus Ruff, dashboard lint/build, and `git diff --check`. A final independent review of
this bypass fix is in progress. The protected migration 013 proposal and assertion hashes are
unchanged.

### 2026-09-02 — Independent local review passed

Independent review re-ran the focused Telegram/Activation path and the complete 235-test backend
suite, inspected the canonical Activation gate and callback exception, and found no remaining
actionable local defect. Ruff, dashboard lint/build, and `git diff --check` also pass. Migration
013 is safe to present for explicit human approval at the recorded hashes. Clean-account desktop
and mobile staging exercise remains rollout evidence rather than a local-code blocker.

### 2026-09-12 — Migration 013 approved and added; schema blocker cleared

The project owner approved migration 013. `migrations/013_dashboard_first_activation.sql`,
`tests/sql/activation_journey.sql`, and `scripts/check_activation_lock_order.py` are checked in and
wired into CI in numeric order. The durable Activation Journey table, the four service-only
functions the staged application already calls, and the acknowledged-Journey gate on
`issue_pairing_token` now exist. See
`.scratch/amigo-internal-preflight/reviews/013-dashboard-first-activation.md`.

Because `get_activation_state` reproduces the derivation in `src/activation.py` and
`src/memory/activation.py`, a differential harness compared the SQL read model against the
in-memory mirror across 16 scenarios covering every journey step, all four Pairing-token states,
every delivery state, and all three resolutions: 16/16 match. The harness found three defects
before review — session-timezone rather than UTC timestamp rendering, a name-normalization
divergence, and an ambiguous `reminder_id` predicate in the assertions.

Independent review then found a blocking defect neither the assertions nor the harness could see:
`create_activation_test_command` took a `user_profiles` row lock before the identity advisory lock
while `get_activation_state` took them in the opposite order, so submitting the test Reminder while
the dashboard polls deadlocked. Measured 88 deadlocks per 300 concurrent calls before the fix and 0
after. `scripts/check_activation_lock_order.py` guards it in CI and fails at 88 on the original
ordering. Review also corrected the database acting as a third name normalizer, and a real crash in
`src/activation.py` where a NULL `deferred_count` raised `TypeError`.

No acceptance criterion is marked complete. Every criterion on this issue describes participant-
visible end-to-end behavior, and the outstanding evidence is the same for all six: a clean synthetic
Dashboard Account completing the journey against separate staging Supabase, Telegram, and dashboard
resources, including actual Telegram delivery and desktop/mobile checks. That evidence cannot be
produced from this worktree and is not simulated here.

### 2026-09-13 — Migration 014 adopted; the schema blocker is cleared

`migrations/014_application_schema_version.sql` is checked in, so the Activation application code
can now boot against a complete chain. A defect in migration 013 found by independent review was
also fixed in the same change: `create_activation_test_command` inverted its row-lock order
against `get_activation_state` and deadlocked when `complete_pairing` landed mid-flight. It now
raises the retryable `activation_pairing_changed` instead, and CI proves the property with a
deterministic forced interleave rather than a random race.

No acceptance criterion changes. Every remaining criterion is clean-account staging evidence on
desktop and mobile, which needs the dedicated staging resources in
`staging-provisioning-checklist.md`.
