# Record Internal Preflight Release Evidence

Status: open
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: unassigned

## What to build

Assemble dated, commit-linked Release Evidence for Internal Preflight and present it for founder
approval. This issue records whether Gate A passes; it does not waive Critical or required High
findings and does not authorize the External Invitation Beta.

## Acceptance criteria

- [ ] Backend and frontend CI are green for the exact release revision, including a clean
  migration setup with Pairing/RLS and the approved model evaluation.
- [ ] Two-participant isolation, fail-closed configuration, Telegram replay, ambiguous-time, and
  scheduler restart evidence is linked and valid for the tested release.
- [ ] Three consecutive staging runs complete Dashboard Account → Pairing → Task → Reminder → Done
  → dashboard synchronization with observable delivery and lateness.
- [ ] Render has one verified webhook/scheduler owner and all public URLs, screenshots, and release
  copy match the capability matrix and tested deployment.
- [ ] Every item records owner, date, tested revision/environment, and evidence link; invalidated
  or missing evidence is visibly not passing.
- [ ] No Critical or Gate-A High finding remains open, and the founder records an explicit pass or
  fail decision without approving their own required independent security review.

## Blocked by

- [Secure Single-Use Pairing Tokens](01-secure-single-use-pairing-tokens.md)
- [Prove Cross-Tenant Isolation](02-prove-cross-tenant-isolation.md)
- [Fail Closed Under Unsafe Production Configuration](03-fail-closed-production-configuration.md)
- [Capture an Inbox Task Through One Shared Command](04-capture-inbox-task-through-shared-command.md)
- [Schedule a Reminder Through the Durable Outbox](05-schedule-reminder-through-durable-outbox.md)
- [Resolve a Task and Reminder Consistently](06-resolve-task-and-reminder-consistently.md)
- [Apply Later Consistently Across Both Surfaces](07-apply-later-across-surfaces.md)
- [Clarify and Confirm Reminder Time](08-clarify-and-confirm-reminder-time.md)
- [Claim and Replay Telegram Updates Safely](09-claim-and-replay-telegram-updates.md)
- [Serve One Consistent Dashboard Snapshot](10-serve-consistent-dashboard-snapshot.md)
- [Recover Reminder Scheduling After Restart](11-recover-reminder-scheduling-after-restart.md)
- [Expose Reminder Delivery, Lateness, and Readiness](12-expose-reminder-delivery-lateness-and-readiness.md)
- [Remove Blocking Supabase Access From the Event Loop](13-remove-blocking-supabase-access.md)
- [Run the Gate A Model Evaluation](14-run-gate-a-model-evaluation.md)
- [Complete the Dashboard-First Activation Journey](15-complete-dashboard-first-activation.md)
- [Verify the Single-Owner Render Staging Path](16-verify-single-owner-render-staging.md)

## Delivery notes

- Affected areas: release checklist, CI results, migration/security review, model evidence,
  staging Core Loop results, deployment ownership, and release-facing artifacts.
- Rollout: evidence review only; Gate B remains closed after Gate A passes.
- Rollback: mark the gate failed or evidence invalid when an input changes or a blocking finding
  appears.

## Comments

