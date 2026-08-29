# Amigo vs OpenHuman — Architecture & Implementation Analysis

> **Internal historical design research.** References to Memory, anti-nag behavior, coaching,
> voice, additional channels, or proactive companion behavior describe hypotheses and roadmap
> ideas—not shipped Amigo capabilities. Use the [capability matrix](capability-matrix.md) for
> current product claims.

## Executive Summary

**Similarity: ~25% overlap.** These projects are in adjacent conceptual spaces but solving fundamentally different problems. OpenHuman is a **privacy-first desktop platform** (Rust core + Tauri shell) that unifies messaging across apps. Amigo is a **proactive AI companion** (Python + FastAPI + Telegram) focused on daily task management and emotional attunement.

**Top 3 ideas worth stealing:**

1. **Event Bus** — OpenHuman's typed `DomainEvent` pub/sub would prevent our `TurnProcessor` from becoming a God object as we add anti-nag, PACT eval, and coaching adaptation. A lightweight Python implementation before Phase 1b is the highest-leverage move.

2. **Structured Memory with Scoring** — Their memory chunks have relevance/recency/importance scores and a "subconscious" reflection system. Directly applicable to our Graphiti integration and the "Amigo notices patterns" goal.

3. **Cron-Driven Intelligence** — OpenHuman uses domain-specific cron subscribers (not just single-fire reminders) for scheduled intelligence runs. Our routine learning, coaching calibration, and PACT evaluation all need this pattern.

---

## TL;DR

These are **fundamentally different products** that share a thin surface-area overlap in "AI companion" branding. OpenHuman is a **privacy-first desktop platform** for unifying messaging, memory, and automation across apps. Amigo is a **proactive AI friend** delivered via Telegram that manages your day. The architectural gulf is massive, but OpenHuman's memory, event, and skill systems contain patterns worth studying.

---

## Similarity Assessment

| Dimension | Alignment | Notes |
|-----------|-----------|-------|
| **Core Goal** | 🔴 Low | OpenHuman = privacy-first desktop AI hub for communities; Amigo = proactive 1:1 companion |
| **Delivery Model** | 🔴 Low | Desktop app (Tauri/Electron) vs. Telegram bot + API server |
| **Architecture** | 🔴 Low | Rust core + React frontend + JSON-RPC sidecar vs. Python FastAPI monolith |
| **Memory System** | 🟡 Medium | Both invest heavily in memory; different approaches |
| **Channel Abstraction** | 🟢 High | Both abstract over messaging platforms (Telegram, WhatsApp, Slack, Discord) |
| **Proactive Behavior** | 🟡 Medium | OpenHuman has cron-driven intelligence; Amigo has scheduled reminders + morning planning |
| **Personality/Soul** | 🟡 Medium | Both define AI persona docs; different execution depth |
| **LLM Routing** | 🟡 Medium | Both route between models; OpenHuman adds local Ollama + Whisper |
| **Privacy** | 🟢 High | Both prioritize user data control; OpenHuman is local-first, Amigo plans Memory Inspector |

**Overall: ~25% overlap** — these are in adjacent conceptual spaces but solving different problems with completely different architectures.

---

## OpenHuman Architecture Summary (Non-UI)

```
┌──────────────────────────────────────────────┐
│              openhuman_core (Rust)            │
│                                              │
│  ┌─────────┐ ┌─────────┐ ┌──────────────┐   │
│  │ Memory  │ │ Agent   │ │ Channels     │   │
│  │ Pipeline│ │ System  │ │ (scanners)   │   │
│  └────┬────┘ └────┬────┘ └──────┬───────┘   │
│       │           │             │            │
│  ┌────┴───────────┴─────────────┴────────┐   │
│  │          Event Bus (DomainEvent)       │   │
│  └───────────────────────────────────────┘   │
│       │           │             │            │
│  ┌────┴────┐ ┌────┴────┐ ┌─────┴──────┐     │
│  │ Cron    │ │ Skills  │ │ Webhooks   │     │
│  │ Jobs    │ │ System  │ │            │     │
│  └─────────┘ └─────────┘ └────────────┘     │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │  JSON-RPC / CLI / Axum HTTP Server   │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
         ↕ JSON-RPC over HTTP
┌──────────────────────────────────────────────┐
│           Tauri Desktop Shell                │
│  (window mgmt, core process lifecycle,       │
│   CEF webviews for messaging apps)           │
└──────────────────────────────────────────────┘
```

### Key subsystems:

- **Memory Pipeline**: SQLite-backed chunked memory with entity extraction, scoring, heatmaps, and a "subconscious" reflection system
- **Event Bus**: Typed pub/sub (`DomainEvent` enum) + native request/response — modules communicate without direct coupling
- **Channel Scanners**: Per-platform Rust modules (WhatsApp, Telegram, Slack, Discord) that scrape via CDP/IndexedDB, not API injection
- **Skills System**: Plugin architecture with registry, install/uninstall, preference persistence, and webhook routing
- **Cron System**: Scheduled intelligence jobs with domain-specific subscriber patterns
- **Local AI**: Whisper (STT), Piper (TTS), Ollama (LLM) — full offline capability

---

## Relevant Ideas for Amigo

### 1. 🏗️ Event Bus Pattern (High Value)

**What OpenHuman does**: A typed `DomainEvent` enum with domains (`agent`, `memory`, `channel`, `cron`, `skill`, `tool`, `webhook`, `system`) and an async pub/sub bus. Modules subscribe to events without knowing about each other.

**Why it matters for Amigo**: Our current `TurnProcessor` is a sequential pipeline — status check → task extraction → morning planning → chat. As we add:
- Anti-nag governor
- PACT evaluation
- Coaching style adaptation
- Routine learning

...this pipeline will become a tangled chain of if-else. An event bus lets each system react independently:

```python
# Instead of sequential checks in TurnProcessor:
class AntiNagSubscriber:
    async def handle(self, event: MessageReceived):
        if self.should_suppress(event.user_id, event.category):
            event.cancel()

class PACTEvaluator:
    async def handle(self, event: SessionClosed):
        scores = await self.evaluate(event.session)
        await self.adjust_parameters(scores)
```

> **Tip**: We don't need Rust-level complexity. A simple Python implementation with `asyncio.Queue` or a lightweight pub/sub library would give us the decoupling benefit at our current scale.

---

### 2. 🧠 Structured Memory with Scoring (High Value)

**What OpenHuman does**: Memory chunks have `score_bars` (relevance, recency, importance), entity extraction, and a "subconscious" reflection system that consolidates memories during idle time.

**What Amigo has**: Linear message storage in Supabase with a session-based context builder (profile → yesterday summary → today tasks → recent messages, capped at 3K tokens).

**Applicable ideas**:
- **Memory scoring**: When we add Graphiti, consider scoring memory chunks by `recency × relevance × emotional_weight`. This feeds directly into our anti-nag system — memories with high emotional weight get more careful handling.
- **Sleep-time consolidation**: OpenHuman's "subconscious" runs background reflection. We've planned this in Phase 2a. Their pattern of using idle-time cron jobs to consolidate and cross-reference memories is exactly what we need for "Amigo notices you've been skipping gym for 2 weeks."
- **Entity extraction on messages**: Rather than just storing raw messages, extract entities (people, places, preferences) into a separate index. This powers our temporal memory goal.

---

### 3. 🔌 Skills/Plugin Architecture (Medium Value)

**What OpenHuman does**: A formal skills system with:
- Registry (local + remote)
- Install/uninstall lifecycle
- Per-skill preferences (`skill-preferences.json`)
- Webhook routing per skill
- Category filtering

**Why it's relevant**: Our Phase 2 plans include coaching style adaptation, voice, and potentially integrations. A plugin model would let us ship these as swappable skills:

```python
class CoachingSkill(AmigoSkill):
    name = "coaching_adaptation"
    triggers = [EventType.SESSION_CLOSED]
    
    async def execute(self, context):
        # Adjust personality axes based on session outcomes
```

> **Note**: This is a Phase 2+ concern. Don't over-architect now, but designing with this in mind means our current agent/turn code stays clean when we add capabilities.

---

### 4. 📡 Channel Scanner Pattern (Medium Value)

**What OpenHuman does**: Each messaging platform (WhatsApp, Telegram, Slack, Discord) gets a dedicated Rust scanner module with:
- DOM snapshot extraction
- IndexedDB reading
- CDP-based interaction (no JS injection)
- Structured message extraction

**What Amigo has**: Clean `MessageChannel` protocol + Telegram implementation.

**Applicable idea**: Our channel abstraction is already good, but OpenHuman's approach of **reading existing conversations** (not just receiving bot messages) is interesting for Amigo's future. If Amigo eventually moves to WhatsApp or monitors other channels, the pattern of scanning existing message databases (rather than relying on webhook delivery) is more resilient.

---

### 5. ⏰ Cron-Driven Intelligence (Medium Value)

**What OpenHuman does**: A full cron system with domain-specific subscribers:
```
CronDeliverySubscriber → handles scheduled jobs
WebhookRequestSubscriber → handles webhook-triggered work  
ChannelInboundSubscriber → handles incoming messages
```

**What Amigo has**: APScheduler for reminders only.

**Applicable idea**: Our anti-nag governor, routine learning, and PACT evaluation all need scheduled intelligence runs that go beyond single-task reminders. A cron abstraction that can run:
- Daily routine confidence scoring
- Weekly coaching calibration
- Session evaluation batches
- Memory consolidation sweeps

...would be cleaner than adding more APScheduler jobs ad-hoc.

---

### 6. 🔐 Controller Schema Pattern (Low-Medium Value)

**What OpenHuman does**: Shared `ControllerSchema` types enforce a contract between the core and all consumers (CLI, JSON-RPC, UI). Every domain exposes its capabilities through a schema registry.

**Why it's interesting**: As Amigo grows beyond Telegram (Flutter app, voice), having a formal schema for what the agent can do would prevent drift between channels. Our `ModelProvider` protocol is a good start, but a schema for the agent's capabilities (available tools, task operations, memory queries) would make multi-channel development safer.

---

### 7. 🗣️ Local AI Fallback (Future Value)

**What OpenHuman does**: Bundles Whisper (STT), Piper (TTS), and Ollama (local LLM). The `.env.example` shows `OPENHUMAN_LOCAL_AI_TIER` presets and binary path overrides.

**What Amigo plans**: Gemini Live API for voice, with Whisper + ElevenLabs fallback.

**Applicable idea**: OpenHuman's approach of **tiered local AI** is interesting for our cost model. Our Phase 1 doc mentions using a "small local model for memory extraction (near-zero cost)." OpenHuman proves this works at production scale with Ollama integration. Consider adding an `OllamaProvider` to our `ModelProvider` protocol for memory extraction work.

---

## What's NOT Applicable

| OpenHuman Feature | Why It Doesn't Apply |
|---|---|
| CDP/Chromium scraping | Amigo doesn't embed other apps |
| Tauri desktop shell | Amigo is server-side, not desktop |
| CEF webview management | Not relevant to bot architecture |
| Crypto payments / rewards | Different monetization model |
| Team management / invites | Amigo is personal 1:1 |
| Meet audio/video pipeline | No real-time call integration |
| Screen capture / intelligence | Desktop-only feature |

---

## Architectural Comparison

| Aspect | Amigo | OpenHuman |
|--------|-------|-----------|
| **Language** | Python 3.12 | Rust (core) + TypeScript (app) |
| **Framework** | FastAPI | Axum (HTTP) + JSON-RPC |
| **Database** | Supabase (PostgreSQL) | SQLite (local) + optional remote |
| **Scheduler** | APScheduler (in-memory) | Cron system with event bus |
| **LLM Integration** | Gemini via google-genai SDK | Multi-provider (cloud + Ollama local) |
| **Memory** | Flat messages + session summaries | Chunked memory with scoring + entities |
| **Channel Abstraction** | Protocol-based (Python typing) | Trait-based (Rust async-trait) |
| **Agent Pattern** | Sequential pipeline in TurnProcessor | Event-driven with DomainEvent bus |
| **Privacy Model** | Cloud-first (Supabase) | Local-first (SQLite on device) |
| **Deployment** | Railway (cloud) | Desktop app (self-hosted) |
| **Maturity** | Early MVP (Phase 1a) | v0.53.46, production desktop app |
| **Codebase Size** | ~15 files, ~60KB | ~200+ Rust files, massive monorepo |

---

## Recommended Priority for Amigo

| Priority | Idea | When |
|----------|------|------|
| 🔴 Now | Event bus pattern (lightweight Python impl) | Before Phase 1b adds anti-nag + PACT |
| 🟡 Phase 1b | Cron-driven intelligence jobs | For routine learning + coaching calibration |
| 🟡 Phase 2a | Memory scoring + entity extraction | When integrating Graphiti |
| 🟢 Phase 2b | Skills/plugin architecture | When adding voice + coaching modules |
| 🟢 Future | Local AI provider (Ollama) | For cost optimization on memory extraction |
