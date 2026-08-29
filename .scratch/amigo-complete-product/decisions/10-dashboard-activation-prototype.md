# Approve the Dashboard-First Activation Journey

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:prototype`
Type: HITL / prototype
Severity: `severity:high`
Owner: Codex
Blocked by: [Lock the Beta Promise and Capability Exclusions](02-beta-promise-and-exclusions.md), [Define the Proportionate Beta Privacy and Retention Contract](04-beta-privacy-retention.md), [Resolve the Task and Reminder Lifecycle](05-task-reminder-lifecycle.md), [Choose the Cross-Surface State Contract](06-cross-surface-state-contract.md)

## Question

What exact account creation, Pairing, profile setup, test Reminder, recovery, return-to-dashboard,
and first-value journey should define Activation on desktop and mobile?

## Comments

### Prototype under review — 2026-08-29

Development-only prototype:
`web/src/prototypes/activation/ActivationPrototype.jsx`, available at
`/?prototype=activation&variant=A|B|C` through `npm run prototype:activation`.

- **A — Focused path:** one primary action at a time with a persistent progress rail.
- **B — Telegram bridge:** dashboard instructions and a live simulated Telegram phone shown
  together so the cross-surface handoff is explicit.
- **C — Activation checklist:** resumable progress embedded in the dashboard shell, with the
  current action expanded beside the full journey.

All variants simulated Account creation, beta-limit acknowledgement, Pairing, profile/timezone,
a two-minute test Reminder, Telegram resolution, and dashboard unlock. They shared in-memory state
and performed no authentication, database, Telegram, or production mutation.

### Resolution — 2026-08-29

Adopt a hybrid journey: Variant A's focused one-primary-action path is the canonical onboarding
experience; Variant B's dashboard/Telegram preview appears only where the participant must cross
surfaces for Pairing and Reminder resolution; Variant C's checklist becomes the recovery view
when a participant returns after interruption.

The Dashboard Account coordinates the journey and stores durable progress. The exact sequence is:

1. Create and verify a Dashboard Account.
2. Review and acknowledge the narrow beta promise, data use/retention, participant rights, and
   non-clinical limitations.
3. Generate one expiring Pairing link and connect Telegram. The dashboard automatically detects
   success; Telegram confirms the linked account without exposing identifiers and offers a return
   link.
4. Resume on the dashboard to set preferred name, explicit IANA timezone, and beta quiet hours.
5. From the dashboard, schedule one clearly labelled private test Task and Reminder for two
   minutes in the future, showing its exact date, local time, and timezone before confirmation.
6. Deliver the test Reminder in Telegram and require the participant to resolve it with Done,
   Skip, or Later. Activation requires a delivered and terminally resolved test Reminder; merely
   scheduling it is not enough.
7. Detect the Telegram result automatically, show the same result on the dashboard, mark
   Activation complete, unlock the normal dashboard, and give one next action: tell Amigo one real
   thing to follow up on.

Persist versioned progress and resume at the first incomplete step on desktop or mobile. Email
verification returns to the journey; an expired/replaced/used Pairing token has a specific
recovery action; a closed dashboard can be reopened from Telegram; and failed or late test
delivery offers retry/support without falsely completing Activation. Desktop uses a compact
progress rail; mobile uses the same focused sequence with a compact progress indicator. The full
checklist is shown only on resume/recovery, not as the default first-time layout.

The throwaway prototype was deleted after this decision was captured. Production implementation
must be rewritten with real state, error handling, accessibility, analytics, and tests.
