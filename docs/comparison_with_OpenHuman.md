# Amigo and OpenHuman — Decision-Aligned Research Note

**Document status:** Historical competitor/architecture research, reconciled with Amigo's
2026-08-29 product decisions on 2026-08-30. OpenHuman details came from the original research
snapshot and have not been revalidated here; they must not be used as current competitive claims.

The [capability matrix](capability-matrix.md) is authoritative for shipped Amigo behavior. The
[complete-product decision map](../.scratch/amigo-complete-product/MAP.md) is authoritative for
future scope.

## Current Amigo baseline

Amigo is a pre-beta AI accountability companion. Its implemented foundation is a Python/FastAPI
service, Pydantic AI tool-calling agent, Telegram adapter, Supabase persistence/authentication,
APScheduler Reminder scheduler, local CLI, and React/Vite dashboard.

The narrow beta promise is conversational Task capture followed by a participant-scheduled
Telegram Reminder with Done, Skip, or Later. The current repository is not evidence of a
production-ready beta, durable personal Memory, adaptive coaching, proactive companionship,
wellbeing services, additional channels, voice, or native mobile support.

## What remains useful from the original comparison

### Explicit domain events

Decoupled events may become useful as the number of durable scheduler effects and operational
signals grows. They are not the current priority or a prerequisite for the beta. The approved
cross-surface contract already requires atomic domain transitions plus a durable scheduler outbox;
that contract should be implemented before introducing a general event bus.

### Structured Memory

OpenHuman's structured-memory concepts remain research input only. Amigo's approved Memory
contract is explicit-first, participant-confirmed, inspectable, correctable, pausable, and
demand-gated. No storage or retrieval technology—including Graphiti, pgvector, an entity graph,
or a scoring formula—has been selected. Technology work begins only after the Memory demand gate
opens and the outstanding technology decision is resolved.

### Plugin or skills architecture

A registry can help when independently releasable capabilities actually exist. Amigo currently
has one narrow Core Loop, so a plugin framework would add structure without validated demand.
Revisit only when a gated capability needs independent lifecycle, permissions, configuration,
and failure isolation.

### Channel adapters

Amigo's `MessageChannel` protocol is intentionally limited to messaging transport. Reading or
scraping unrelated existing conversations is not part of Amigo's approved product or privacy
contract. WhatsApp remains **No Expansion Yet** and requires observed recruitment friction plus a
closed integration-contract ticket before implementation.

### Scheduled intelligence and local models

The beta requires reliable participant-scheduled Reminders, reconciliation, metrics, and one
always-on scheduler owner. General cron-driven intelligence, background reflection, routine
learning, local model fallbacks, and proactive check-ins are not approved beta capabilities.
Provider or model changes also require configuration work and a new model-evaluation run; they are
not drop-in product changes.

## Current architectural contrast

| Dimension | Amigo now | OpenHuman research snapshot |
|---|---|---|
| Product shape | Hosted accountability companion using Telegram plus a paired dashboard | Privacy-first desktop platform aggregating messaging and local capabilities |
| Runtime | Python 3.12, FastAPI, Pydantic AI | Rust core with a desktop shell |
| Persistence | Cloud-hosted Supabase/PostgreSQL | Primarily local storage |
| Scheduling | In-process APScheduler with database reload; durable outbox still planned | Broader cron/event infrastructure |
| Memory | Messages, Tasks, Sessions, and summaries; not the approved durable Memory product | Structured local memory concepts |
| Extensibility | Narrow protocols and injected Tools | Broader skills/plugin architecture |
| Release state | Pre-beta; Gate A and Gate B evidence incomplete | External project state not revalidated in this document |

## Decision-aligned priority

1. Make the Telegram Core Loop conform to the approved Task/Reminder lifecycle.
2. Implement authenticated shared commands, idempotency, durable effects, reconciliation, and one
   consistent dashboard snapshot.
3. Close pairing/RLS, production configuration, privacy/data-rights, observability, capacity, and
   model-evaluation gates.
4. Implement and validate the Dashboard-first Activation Journey.
5. Collect beta evidence before opening Memory, Modes, wellbeing, WhatsApp, voice, PWA, or native
   mobile work. **No Expansion Yet** remains the current portfolio decision.

The useful lesson from the comparison is architectural restraint: borrow a pattern only when an
approved capability and measured failure mode justify it.
