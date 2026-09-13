# Staging Provisioning Checklist

Prepared: 2026-09-12

The schema chain and local product paths are implemented, but the remaining work is not purely
staging evidence. Issue 15 still requires a published, founder-approved privacy/terms notice before
Pairing. Issues 13–17 also require the external resources and evidence listed below. This checklist
records what must exist before those criteria can be satisfied; local tests are not substitutes.

Production must not be used for any of it. Issues 16 and 17 require separate resources, and the
synthetic failure, replay, and load work would otherwise touch real participants.

## 1. Non-production Render backend and dashboard

Unblocks: issue 13 (deploying and measuring baseline/candidate revisions), issue 16 (all six
criteria), issue 17 (Render owner criterion).

- A staging backend and a staging static dashboard, each distinct from production and on its own
  URL. The backend must use a non-sleeping, always-on plan; the blueprint's current free plan is
  not sufficient for Reminder evidence.
- Backend: `APP_ENV` set to a non-production value, `APP_BASE_URL` set to the staging backend,
  `DASHBOARD_URL` set to the staging dashboard, and only staging provider credentials.
- Dashboard: `VITE_API_URL` set to the staging backend and `VITE_SUPABASE_URL` plus
  `VITE_SUPABASE_ANON_KEY` set to the staging Supabase project. It must not reference a production
  URL or credential.
- Ability to trigger a deployment restart on demand, for the before/after single-owner and restart
  recovery evidence.
- Access to liveness, readiness, and application error output for the tested revision.

## 2. Separate staging Supabase project

Unblocks: issue 13 (latency measurement), issue 15 (clean-account journey), issue 16, issue 17.

- A project distinct from production, with its own `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.
- Migrations 001 through 014 applied in numeric order, so `get_app_schema_version` reports exactly
  14 and the startup gate passes.
- Supabase Auth email delivery working, since the Activation Journey begins at a verified
  Dashboard Account.

## 3. Dedicated staging Telegram bot

Unblocks: issue 15 (actual delivery), issue 16 (webhook owner, restart recovery), issue 17.

- A bot token separate from production, with its webhook pointed only at the staging service.
- `TELEGRAM_WEBHOOK_SECRET` set for the staging service.
- Confirmation that no other deployment holds a webhook on the same bot, since the single-owner
  criterion is about exactly one active webhook destination.

## 4. Separate quota-capable staging model resource

Unblocks: issue 14 (the declared Gate A runs), issue 16 (separate model-resource criterion),
issue 17 (approved model evaluation).

- A dedicated staging model project and `GOOGLE_API_KEY`, separate from production, with billing
  or quota sufficient for the declared run. The current development key exhausted its 20-request
  daily quota during probes.
- Use the exact release model/version and settings required by issue 14; separate credentials must
  not silently change the evaluated model contract.
- Each run is 60 cases at three repetitions. Because no passing baseline artifact exists yet, the
  first gated release needs one full baseline-establishment run and then one distinct candidate
  run. A failed candidate must not be retried unchanged for a lucky pass, so the credential must
  carry both full runs plus any permitted post-change replacement.

## 5. Test identities

Unblocks: issue 15, issue 16, issue 17.

- At least one synthetic clean account: an email address that has never been through Activation,
  plus a Telegram account that has never paired.
- A second identity for the two-participant isolation evidence.
- Issue 17 asks for three consecutive staging Core-Loop runs, which needs either three clean
  identities or a documented reset procedure between runs.

## 6. Independent human security reviewer

Unblocks: issue 17 (final criterion).

- A reviewer distinct from both the release implementer and founder. The implementer may produce
  evidence and may review records produced by someone else, but cannot review their own record or
  serve as the independent security reviewer; the founder also cannot serve as that reviewer.

## 7. Founder-approved privacy, terms, and support notice

Unblocks: issue 15 (pre-Pairing acknowledgement), issue 17 (public surfaces/release copy).

- Publish the approved data inventory, purposes, retention schedule, processors and cross-border
  processing, participant rights, withdrawal/deletion path, age 18+ eligibility, and warning not
  to share medical, financial, identity, emergency, or sensitive third-party information.
- Publish the invitation-beta participation terms and non-clinical/product limitations.
- Provide the real dedicated privacy/support contact and obtain the required human review. Do not
  ship placeholder contact details or agent-invented legal assurances.
- Link the reviewed version from Activation before Pairing and preserve its immutable policy
  version in the existing acknowledgement record.

## What happens once these exist

After prerequisite provisioning and the reviewed consent notice, issues 13, 14, and 15 can gather
their independent evidence in parallel. Issue 16 depends on issues 13 and 15; issue 17 depends on
all prior preflight issues.

1. Provision the separate resources, publish/review the privacy and terms notice, apply migrations
   001–014 to staging Supabase, and confirm the startup gate passes.
2. In parallel where practical:
   - Issue 13 — deploy the documented baseline and candidate revisions and measure event-loop delay
     and database latency under the exact concurrent Turn/due-Reminder workload.
   - Issue 14 — establish the first passing Gate A baseline, run a distinct candidate against the
     release model, then independently review the comparison evidence.
   - Issue 15 — exercise clean-account Activation on desktop and mobile, including reviewed
     consent, real Telegram delivery, and Done/Skip/Later resolution in the dashboard snapshot.
3. Issue 16 — after issues 13 and 15 pass, verify the single owner and webhook destination, restart
   and verify again, capture
   recovery/observability evidence, and run the clean-account Core Loop.
4. Issue 17 — after every dependency passes, assemble artifacts for one exact revision/deployment,
   run
   `scripts/validate_preflight_evidence.py`, obtain the independent security review, then record
   the founder's explicit pass or fail decision.

Issue 17 can close Gate A only. It does not authorize the External Invitation Beta. Gate B remains
closed until its separate usability, privacy-rights/export/deletion, capacity/limits, monitoring,
support, and other approved criteria pass.
