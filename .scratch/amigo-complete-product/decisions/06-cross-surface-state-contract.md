# Choose the Cross-Surface State Contract

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:prototype`
Type: HITL / prototype
Severity: `severity:high`
Owner: unassigned
Blocked by: [Resolve the Task and Reminder Lifecycle](05-task-reminder-lifecycle.md)

## Question

What authenticated mutation and read-model contract keeps Telegram, dashboard, persistence, and
the scheduler consistent while preserving ADR-0002's Tool boundary and tenant ownership?

## Comments

### Resolution — 2026-08-29

Adopt a transactional command plus durable scheduler-outbox contract. Persistence is the system
of record; APScheduler is a rebuildable delivery projection. Telegram and dashboard are adapters
to the same authenticated application commands and server-derived reads.

The throwaway logic prototype compared inline database-plus-scheduler writes with an outbox under
scheduler failure, replay, surface switching, and a cross-tenant mutation attempt. Inline writes
could acknowledge the old Reminder, fail before creating/scheduling its replacement, and then
deduplicate the replay—losing the participant's `Later` intent. The transactional outbox retained
the complete transition and recovered idempotently when scheduling returned. The prototype was
removed after these findings were captured, as required for throwaway code.

#### Boundaries

```text
Telegram adapter ─┐
                  ├─> authenticated application command ─> Tool/domain operation
Dashboard API  ───┘                                      └─> transactional Store operation
                                                                  ├─> Task/Reminder rows
                                                                  ├─> command receipt
                                                                  └─> scheduler outbox

outbox worker ─> APScheduler projection
reconciler    ─> database authority vs APScheduler projection
dashboard     <─ one authenticated server-derived snapshot
```

- ADR 0002 remains authoritative: the agent may choose Tools, but side effects occur only through
  injected services. Dashboard endpoints and agent Tools share an owned application command
  service/domain operation; the dashboard does not invoke the model and neither surface writes
  Task/Reminder tables directly.
- Store access remains behind `MemoryStore`. Transactional methods must remain behaviorally
  mirrored in `InMemoryStore` and `FakeStore`.
- The browser may keep Supabase Auth. It must not independently query or mutate product tables.
  A realtime subscription, if retained, is only an invalidation hint that triggers a fresh
  snapshot; its payload is not merged into application state.

#### Authentication and ownership

- The dashboard adapter verifies the bearer token and resolves `auth.uid()` to the paired
  `user_id`. The Telegram adapter resolves the verified chat identity to the same `user_id`.
- `user_id` is injected into the command context and is never accepted from browser, Telegram,
  model, or Tool arguments supplied as user-controlled identity.
- Every command checks aggregate ownership in its database transaction. Database functions used
  by the service role must be unavailable to anonymous/authenticated client roles and must include
  explicit actor/row ownership predicates rather than relying on service-role RLS behavior.
- Resource-not-found and wrong-owner cases expose the same safe response and do not mutate state.

#### Command contract

Expose typed authenticated commands for Create Task, Complete Task, Skip Task, Cancel Task,
Schedule/Reschedule Reminder, Cancel Reminder, and Apply Later. A command contains:

- An adapter-injected actor and source surface.
- A unique idempotency key.
- Typed domain input and resource identifiers.
- An expected aggregate version where the client can possess one.

Dashboard requests generate an opaque UUID `Idempotency-Key`. Telegram message/Tool commands and
callbacks derive stable keys from the claimed update/callback identity plus the command position.
A unique `(user_id, idempotency_key)` command receipt stores a payload hash and response. Replaying
the same key and payload returns the stored response without reapplying effects; reusing the key
with different input returns `409 Conflict`.

Dashboard mutations include the Task/read-model version they observed. A stale version returns
`409 Conflict` with the current resource version. Telegram callbacks target an immutable Reminder
identity and perform a conditional transition, making repeated or stale button presses safe and
returning the already-resolved outcome.

#### Transaction and outbox

- Each command atomically writes its Task/Reminder transitions, new aggregate version, command
  receipt/result, and required scheduler effects. No database state is committed without a durable
  record of every required schedule/cancel effect.
- Implement the beta transaction boundary with reviewed, narrowly scoped PostgreSQL RPC/functions
  called only through `MemoryStore`, unless a later ADR deliberately introduces an async direct
  database transaction layer. Multiple independent Supabase REST writes are not a transaction.
- Outbox effects have stable unique identities and record type, actor/aggregate/Reminder IDs,
  payload, attempt state, availability time, and processing timestamps. The worker atomically
  claims effects, applies stable APScheduler job IDs, and records completion. Applying the same
  effect more than once is harmless.
- A committed command with pending delivery effects returns `202 Accepted` plus the canonical
  resource/result, snapshot version, exact intended Reminder time, and effect state. It is valid
  to say the Reminder is saved/scheduled; do not claim channel delivery before it occurs.
- Failed transaction validation changes nothing. A delayed outbox effect never rolls back the
  user's durable command. Poison effects become observable failures and remain reconcilable rather
  than being discarded.

#### Scheduler authority and reconciliation

- The database is authoritative. APScheduler contains exactly one job for each Reminder whose
  canonical state requires future delivery, using a stable `user_id:reminder_id` job ID.
- Reconciliation creates/repairs missing or wrongly timed jobs and removes jobs for missing,
  terminal, or wrong-owner Reminders. It records discrepancies and results for operations evidence.
- Worker/outbox lag, oldest pending effect, failed effect count, reconciliation drift, and
  Reminder lateness are observable. Ticket 20 defines the quantitative Reminder reliability
  denominator and provider exclusions.

#### Read-model contract

`GET /api/dashboard` returns one tenant-scoped, versioned snapshot assembled server-side from one
consistent database view/transaction. It includes at least:

- `snapshot_version`, `generated_at`, current IANA timezone, and local planning date.
- Today's Tasks and progress from exactly the same population.
- Inbox and Carried over Tasks as separate populations.
- Active, delayed, missed, and recently resolved Reminders joined to owned Tasks.
- Recent Sessions translated into customer-readable state.
- Per-resource versions and any scheduling/reconciliation state the participant needs to see.

Mutation responses return the resulting resource plus snapshot/resource version; the dashboard
then refreshes the snapshot. Clients replace older snapshots atomically and never merge fields
from snapshots with different versions. Pagination can be added later for history, but the core
activation snapshot remains one coherent contract.

#### Consequences

- Current direct browser queries/writes, independent Task/Reminder/Session fetches, and browser
  calculation of daily progress do not conform and must be removed.
- Current Tools that perform several independent Store and scheduler calls do not provide the
  required atomicity. Refactor them around transactional Store commands and the outbox rather than
  adding compensation as the primary correctness mechanism.
- The required schema/functions/outbox are production-affecting migrations and therefore require
  explicit human review under repository guardrails.
- “Define transaction/compensation” and “choose snapshot contract” are no longer open design work.
  Implementation issues should build and verify this contract, including failure injection,
  idempotency, tenant isolation, stale-version conflicts, outbox replay, and reconciliation.
