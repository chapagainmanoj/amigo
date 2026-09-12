# Staging Provisioning Checklist

Prepared: 2026-09-12

Every acceptance criterion still open on issues 13, 14, 15, 16, and 17 is an evidence criterion,
not a code criterion. After migration 014 is approved the schema chain is complete and the local
work is finished; nothing further can be closed from this worktree. This lists exactly what has to
exist before that evidence can be produced, and which criteria each item unblocks.

Production must not be used for any of it. Issues 16 and 17 require separate resources, and the
synthetic failure, replay, and load work would otherwise touch real participants.

## 1. Non-production Render service

Unblocks: issue 16 (all six criteria), issue 17 (Render owner criterion).

- A second Render service from the existing `render.yaml` blueprint, on its own URL.
- `APP_ENV` set to something other than `production`, and `APP_BASE_URL` set to the staging URL.
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

## 4. Quota-capable release-model credential

Unblocks: issue 14 (the declared 180-execution run), issue 17 (approved model evaluation).

- A billing-enabled or higher-quota `GOOGLE_API_KEY`. The current key is free tier and exhausted
  its 20-request daily quota during development probes.
- The run is 60 cases at three repetitions. A failed candidate must not be retried unchanged for a
  lucky pass, so the credential needs to carry the whole run.

## 5. Test identities

Unblocks: issue 15, issue 16, issue 17.

- At least one synthetic clean account: an email address that has never been through Activation,
  plus a Telegram account that has never paired.
- A second identity for the two-participant isolation evidence.
- Issue 17 asks for three consecutive staging Core-Loop runs, which needs either three clean
  identities or a documented reset procedure between runs.

## 6. Independent human security reviewer

Unblocks: issue 17 (final criterion).

- A person other than the founder. Issue 17 explicitly forbids the founder approving their own
  required independent security review.

## What happens once these exist

The order follows the issue dependencies:

1. Apply migrations 001–014 to staging Supabase and confirm the startup gate passes.
2. Issue 16 — deploy, verify single owner and webhook destination, restart, verify again, capture
   restart recovery and observability evidence, run the clean-account Core Loop.
3. Issue 13 — measure event-loop delay and database latency before and after under concurrent Turn
   and due-Reminder traffic.
4. Issue 15 — clean-account Activation on desktop and mobile, including real Telegram delivery and
   Done/Skip/Later resolution reflected in the dashboard snapshot.
5. Issue 14 — the full Gate A run against the release model.
6. Issue 17 — assemble every artifact for one exact revision and deployment, run
   `scripts/validate_preflight_evidence.py`, obtain the independent security review, then record
   the founder's explicit pass or fail decision.

Gate B stays closed until issue 17 passes.
