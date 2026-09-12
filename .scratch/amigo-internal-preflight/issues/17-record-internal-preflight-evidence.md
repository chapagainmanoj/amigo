# Record Internal Preflight Release Evidence

Status: open
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: Codex

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

### 2026-09-02 — Fail-closed evidence contract prepared

`docs/internal-preflight-evidence.md` now defines the capture procedure, and
`scripts/validate_preflight_evidence.py` rejects a Gate A pass unless one exact staging revision
has complete dated/owned/linked evidence for CI, migrations, model evaluation, isolation,
fail-closed configuration, replay, time ambiguity, restart recovery, observability, delivery,
lateness, single Render/webhook ownership, separate staging resources, public surfaces, and
independent security review. It additionally requires three consecutive clean-account Core Loop
runs with no lost, duplicate, or cross-participant effect, zero open Critical/Gate-A High
findings, and an explicit founder pass recorded by someone other than the independent security
reviewer.

Missing, unknown, stale, mismatched, self-reviewed, or explicitly failed evidence remains visibly
not passing. Contract regressions cover a complete pass, missing/unknown evidence, topology/Core
Loop failure, revision mismatch, self-review, and founder failure. Local verification passes with
246 backend tests, Ruff, and `git diff --check`. This prepares evidence capture but does not close
the issue: the exact release CI/model/migration artifacts, three staging trials, and founder
decision do not yet exist.

Independent adversarial review initially rejected the checker because shaped-but-invalid dates,
nonexistent artifact strings, repeated trial evidence, and implementer self-review could be
declared passing. The checker now parses real UTC instants, enforces release ordering and
observation windows, binds every record to the exact Render deployment, verifies local artifact
existence and SHA-256 within the manifest directory, requires distinct ordered hash-chained trial
runs, records producer and independent reviewer roles, prevents implementer security self-review,
and requires the founder decision to follow all reviewed evidence. A second independent verdict
is pending on this hardened contract.

The hardened review also found that casing and surrounding whitespace could alias one person as
multiple actors. Actor and trial-run identifiers are now required to be canonical lowercase
stable IDs, and all independence/uniqueness comparisons use their normalized form. The direct
alias regression covers implementer, producer, reviewer, security reviewer, founder, decision
witness, and repeated run IDs.

Final independent adversarial review passed. The reviewer reproduced the original alias exploit
and confirmed it now fails alongside invalid/reversed/out-of-window time, absent or digest-mismatched
artifacts, revision/deployment mismatch, duplicated or unchained trials, self-review, and founder
failure. The evidence-contract slice is locally complete; semantic review of the eventual artifacts
remains intentionally human.

### 2026-09-02 — Local CI surface and documentation audited

The workflow now includes locked frontend install, lint, and production build alongside backend
lint, tests, checked-in PostgreSQL migrations/security assertions, and Gate A contract validation.
Backend 252 tests, Ruff, frontend lint/build, workflow parsing, and whitespace checks pass locally.
An independent review also passed the release-document consistency audit.

This is preparation, not release evidence. Checked-in CI currently stops at approved migration
011 while the staged application fails closed unless schema version 14 is present. The exact
release CI criterion cannot pass until protected migrations 012–014 are approved, checked in with
their assertions, and exercised for the final revision; model, staging trials, topology, public
surface, independent security, and founder-decision evidence also remain absent.

### 2026-09-12 — Chain now reaches 013; evidence set still cannot be assembled

Migrations 012 and 013 are approved, checked in, and wired into CI in numeric order with their
assertion files, and migration 013 also added a CI deadlock guard. The earlier comment on this
issue stating that the release CI criterion cannot pass until protected migrations 012–014 are
approved is superseded in part: 012 and 013 are in, and only 014 remains unapproved. Until 014 is
added, CI still builds a database that the application's exact schema-14 startup gate rejects, so
the first acceptance criterion still cannot pass.

The other five criteria are unchanged and remain blocked on resources this worktree cannot provide:
three consecutive staging Core-Loop runs with observable delivery and lateness, a verified single
Render webhook/scheduler owner with public URLs and screenshots matching the capability matrix, a
completed Gate A model-evaluation run against a quota-capable release credential, an independent
human security review that the founder does not approve themselves, and the founder's recorded
pass/fail decision.

Per this issue's own contract, missing evidence stays visibly not passing. No criterion is marked
complete, and Gate B remains closed.
