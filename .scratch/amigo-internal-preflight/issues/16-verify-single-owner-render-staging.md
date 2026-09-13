# Verify the Single-Owner Render Staging Path

Status: open
Label: `ready-for-human`
Severity: `severity:high`
Type: HITL
Owner: Codex

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

### 2026-09-02 — Local topology preparation started

The repository contradicted its Render-only beta decision: a root `fly.toml` and manually
runnable `.github/workflows/deploy.yml` still provided an executable competing Fly webhook and
scheduler path. Both are now preserved only as explicitly disabled historical files outside their
default executable locations. Static topology regressions require no root Fly configuration, no
active workflow referencing `flyctl` or `FLY_API_TOKEN`, and exactly one Telegram application
owner in the Render blueprint.

Local verification passes with 238 backend tests, Ruff, and `git diff --check`. This closes only
the repository-side competing-owner risk. The issue remains blocked on approved migrations 012
and 013, a schema-version startup/deploy check, dedicated staging resources, an always-on Render
plan, provider access, and the required deployment/restart/Core Loop evidence.

Independent review passed after hardening the regression guard to scan nested non-archive Fly
configuration, active workflows and scripts for Fly deployment markers, and every Render service
block including backends that rely on the default Telegram channel.

### 2026-09-02 — Exact schema startup gate proposed for review

Application startup now connects to the Store and requires exact schema version 14 before
starting APScheduler, draining the outbox, restoring pending Reminders, or setting the Telegram
webhook. Production reads the marker only through a service-role function; `InMemoryStore` and
`FakeStore` mirror strict integer/mismatch behavior. Regressions prove strings, booleans, missing,
older, and newer versions fail closed, and a mismatch produces no scheduler/outbox side effect.

No protected migration file has been added. Exact review artifacts:

- `/tmp/amigo-migration014-proposal.sql` — SHA-256
  `43e26e5363320e8441f5465167a6a9a89c7e29a6b0782bd3ca248cd17995bec9`
- `/tmp/amigo-migration014-assertions.sql` — SHA-256
  `06be28fed547d14b83aaa07409b60e5d5ffdff710c29a5950369c324fd00e807`

A disposable PostgreSQL 15 database passed the clean migration 001–014 chain and marker/RLS/ACL
assertions. The complete backend suite passes with 252 tests, plus Ruff and `git diff --check`.
Independent code and migration review is in progress; explicit human approval is still required
before adding migration 014.

Independent review passed with no actionable code or migration finding. It verified startup
ordering, exact-type/version failure, Store parity, forced RLS, absence of direct table readers,
the service-only hardened accessor, and a live version-14 read from the populated disposable
database. The reviewer could not complete a separate fresh-chain execution because its psql
command waited on sandbox approval; the implementation-side clean 001–014 PostgreSQL run passed.
Migration 014 is safe to present for approval at the recorded hashes. The disposable server was
stopped after review.

### 2026-09-02 — CI and release-document consistency prepared

CI now has an independent frontend job using Node 22, the committed lockfile, `npm ci`, ESLint,
and the production build. Release-facing documentation now describes Render as the sole active
path, the canonical Activation/Reminder behavior, and the distinction between local
implementation and staging evidence. It also fails honestly at the current schema boundary:
checked-in setup and CI stop at approved migration 011 while staged startup requires exact schema
14. This worktree is explicitly documented as non-deployable until protected migrations 012–014
and their assertions are approved and added in order.

Local verification passes with 252 backend tests, Ruff, frontend lint/build, workflow YAML
parsing, and `git diff --check`. Independent documentation/CI review passed after correcting stale
Later, security, generated-dependency, migration, Activation-shipping, and timestamp claims. The
exact-release CI and Render staging acceptance criteria remain open.

### 2026-09-11 — Migration 012 added; 013 and 014 still absent

Migration 012 was approved by the project owner and added with its assertions, CI chain entry, and
README step. The earlier comments on this issue that describe the chain stopping at approved
migration 011, and that name migrations 012–014 collectively as unapproved, are superseded: the
outstanding protected migrations are now 013 and 014 only.

This worktree is still explicitly non-deployable. `src/schema.py` requires exact schema version 14,
`src/startup.py` enforces it before any scheduler-owned side effect, and `get_app_schema_version`
is defined in no checked-in migration. All real Render, staging, restart, and Core-Loop evidence
for this issue remains missing.

### 2026-09-12 — Migration 013 added; first criterion verifiable locally, rest need staging

Migration 013 is approved and checked in, so the chain now reaches 013. Migration 014, which
supplies `get_app_schema_version`, is written and independently reviewed but not yet approved, so
the exact schema-14 startup gate still cannot pass against a database built from this chain.

The first acceptance criterion is the only one provable from this worktree, and it now holds:
`fly.toml` is absent from the active location and preserved as `deploy/archive/fly.toml.disabled`,
the Fly workflow is preserved as `.github/archive/deploy-fly.yml.disabled`, `render.yaml` is the
only active blueprint, and `tests/test_deployment_topology.py` passes. It is left unchecked only
because the criterion also asserts Render is the active beta-intended platform, which is a
statement about a real deployment rather than about the repository.

The remaining five criteria require a real non-production Render deployment: separate Telegram,
Supabase, dashboard, and model resources; a verified single scheduler owner and webhook destination
before and after a restart; restart recovery without duplicate, cross-participant, or lost
delivery; observable liveness, readiness, errors, delivery, and lateness; and a synthetic clean
account completing the Core Loop. None of that is simulated or claimed here.

### 2026-09-13 — Migration 014 adopted; exact-version startup gate is now satisfiable

`migrations/014_application_schema_version.sql`, `tests/sql/app_schema_version.sql`, and
`scripts/check_schema_chain.py` are checked in and wired into CI. The chain guard proves both
directions the in-database assertions cannot: 014 refuses each of the eight constructible
incomplete chains, and the ledger head is compared with `EXPECTED_SCHEMA_VERSION` so a migration
applied without its row — which fails open by reporting a lower revision — is caught.

Independent review found and blocked a security defect in the previously approved bytes: the
`REVOKE` omitted `service_role`, which the Supabase role bootstrap grants full DML on every new
table, so the application's own credential could rewrite the ledger its startup gate reads. Fixed
and asserted before adoption.

One open risk belongs to this issue: the gate has never run against a real PostgREST.
`MemoryStore.verify_schema_version` passes `result.data` into a check that demands an exact `int`,
and no other scalar RPC exists in the codebase to infer the response shape from. If PostgREST
returns `[14]` or an object, startup fails closed on every boot against a correct database. Verify
this first when staging exists.

No acceptance criterion changes; all six remain real-deployment evidence.
