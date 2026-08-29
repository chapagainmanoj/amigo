# Choose the Runtime I/O and Capacity Strategy

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:grilling`
Type: HITL / grilling
Severity: `severity:high`
Owner: Codex
Blocked by: [Define Release Evidence and Gate Thresholds](01-release-evidence-and-gates.md), [Capture the Render and Supabase Runtime Baseline](07-runtime-baseline.md)

## Question

Given the measured baseline, should Amigo adopt an async Supabase client or a bounded worker
adapter, and what concurrency, backpressure, Render resource, and beta-capacity limits follow?

## Comments

### Decision 1 — development versus external-beta runtime

- During development, Amigo may continue using the current free Render service and Supabase
  project. Render sleep/wake delays and unreliable scheduled execution are accepted development
  limitations; this environment must not be presented as continuously available or reminder-safe.
- The runtime must be upgraded **before the first external beta participant is invited**, not after
  real-user failures reveal the need. The external-beta gate requires an always-on runtime,
  database I/O that does not block the event loop, latency and reminder-delivery instrumentation,
  and a passing representative burst test.
- “Real users” in this decision means participants in the External Invitation Beta. Development
  dogfooding does not satisfy or trigger the external-beta runtime gate.

### Decision 2 — database I/O strategy

- Adopt the Supabase SDK's native `AsyncClient` as the canonical database client. All store and
  authentication operations on async request, turn, and scheduler paths must await native async
  calls.
- Keep all product-data access behind `MemoryStore`, including the previously approved narrow
  transactional RPC/functions. The async migration must preserve parity with `InMemoryStore` and
  `FakeStore` wherever their shared contract changes.
- A bounded thread/worker adapter is permitted only as a documented temporary compatibility
  fallback for a specific SDK operation that cannot use the async client. It is not a parallel or
  permanent database architecture.
- Add regression coverage that detects synchronous Supabase execution returning to event-loop
  paths. Changes to the protected singleton wiring in `src/db/supabase.py` require human review.

### Decision 3 — provisional beta concurrency and backpressure

- Serialize Turns per Beta Participant: at most one active Turn per user, preserving accepted
  message order.
- Allow at most four active chat/model Turns globally and 20 waiting Turns. At capacity, fail
  closed with a friendly retry-later response rather than creating an unbounded in-memory queue.
- Allow at most 12 concurrent Supabase operations globally.
- Process reminder and durable-outbox effects through a separate higher-priority lane with four
  workers and capacity for 100 pending effects. Chat/model traffic must not consume this capacity
  or starve reminder delivery.
- Run exactly one application/scheduler owner during the invitation beta. Do not horizontally
  scale this topology until the durable outbox and single-owner/lease contract make ownership
  explicit and tested.
- Instrument active operations, queue depth, queue wait, capacity rejections, database latency,
  and reminder lateness. These limits are conservative starting values for 5–10 participants,
  not certified capacity; the representative burst gate must validate and may lower or raise
  them before invitations are sent.

### Decision 4 — external-beta runtime topology

- Keep the existing free Render service in Singapore for development only.
- Before inviting the first Beta Participant, deploy one always-on paid Render instance with at
  least 0.5 CPU and 512 MB RAM in Oregon, or the closest available US-West Render region, beside
  the existing Supabase project in Oregon.
- Keep exactly one instance/application-scheduler owner during the beta. Scaling out is blocked
  until the durable outbox and ownership/lease contract are implemented and validated.
- Do not add a Fly.io migration to the beta critical path. Re-evaluate hosting only when measured
  demand, availability, cost, or operational constraints justify it.

### Resolution — 2026-08-29

#### Representative Gate-B burst

Run the mixed staging burst three consecutive times on the selected beta Render service. Represent
10 authenticated participants; submit five simultaneous Turns with ordered per-user follow-ups;
request 10 authenticated dashboard snapshots within one minute; and make 10 Reminders due within
that minute, including five while model Turns are active. Include a duplicate webhook delivery and
one transient database/provider failure.

Each run passes only with no lost, duplicate, cross-user, or incorrectly ordered effect; no
unexpected error, timeout, process restart, or capacity rejection; event-loop delay p95 at or
below 50 ms and maximum at or below 250 ms; accepted-Turn-to-response p95 at or below 15 seconds
and maximum at or below 30 seconds; and healthy-provider Reminder lateness p95 at or below 10
seconds and maximum at or below 30 seconds. CPU and memory each retain at least 20% headroom,
connections do not exhaust, queues drain fully, and the injected failure is detected, retried only
within policy, and reconciled without duplicate effects.

This is the representative invitation-beta gate, not a broad capacity certification. A longer
soak and larger capacity test remain required before expanding beyond the first cohort. Burst
evidence expires under the conditions defined in ticket 01.
