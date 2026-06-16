# Amigo — Implementation Plan

An AI companion that acts as a proactive virtual friend: plans your day, sends reminders, and evolves into a memory-rich conversational partner.

---

## Current State

Phase 1a MVP is **shipped and dogfooding**. Core loop works: Telegram bot + CLI, task extraction, reminders with snooze, morning planning, onboarding, session management. 62 tests passing, lint clean.

Key recent fixes:
- APScheduler UTC timezone fix (was defaulting to system tz)
- LLM-based task extraction replaced brittle heuristic
- Time-aware system prompt (greets appropriately for time of day)
- Task title context passed to reminder time resolution (AM/PM disambiguation)
- Dead code cleanup (removed unused `TaskMatcher.looks_like_task_list`, handler wrappers, bot/task_matching.py shim)

### Architecture Decision Records

- [ADR 0001](docs/adr/0001-separate-bot-agent-tools.md) — Bot/Agent/Tools separation (superseded)
- [ADR 0002](docs/adr/0002-agentic-tool-calling-loop.md) — Agentic tool-calling loop (current)

### Domain Glossary

See [CONTEXT.md](CONTEXT.md) for canonical terminology (Turn, Step, Tool, Task, Reminder, Session, TurnContext, ToolContext).

---

## Phase 1 — Agentic Refactor + Production Readiness

### 1.1 Agentic Tool-Calling Loop (ADR 0002)

Collapse sequential chain-of-LLM-calls into a single Pydantic AI `Agent` with native tool calling. See [decision summary](docs/adr/0002-agentic-tool-calling-loop.md) for full rationale.

**Phased rollout:**

#### Step 1: Swap to Pydantic AI Agent

- [ ] Create `TurnContext` dataclass (user, session_id, session_type, is_new, timezone, pending_tasks, chat_id, is_proactive)
- [ ] Create `ToolContext` dataclass (user_id, chat_id, session_id, timezone)
- [ ] Rewrite `AmigoAgent` around `pydantic_ai.Agent` with tools:
  - `create_task(title, category, reminder_time?)` — auto-schedules if time provided
  - `update_task_status(task_id, new_status)` — validates ownership + updatable state, auto-cancels reminders
  - `schedule_reminder(task_id, time_expression)` — for existing tasks
  - `cancel_reminders(task_id)` — explicit cancel
- [ ] Merge `plan_message()` + `chat()` → single `handle_message(turn_context)` returning reply string
- [ ] Morning planning becomes a prompt fragment based on `turn_context.is_new` + `session_type`
- [ ] Simplify `TurnProcessor.handle()`: get session → build TurnContext → call agent → send reply
- [ ] Inject pending tasks with IDs into system prompt (model picks task_id directly)
- [ ] Wrap Pydantic AI behind Amigo-owned interface (no pydantic_ai imports in bot/)
- [ ] Add loop guards: max 10 tool calls/turn, max_retries=3, max_result_retries=1

#### Step 2: Deterministic Time Resolution

- [ ] Add `dateparser` dependency
- [ ] Implement time parsing in `schedule_reminder` tool:
  - `dateparser` first pass
  - Category-aware AM/PM rules (dinner → PM, breakfast → AM)
  - On failure → return error observation → model asks user
- [ ] Delete `REMINDER_TIME_PROMPT` and `ReminderTimeResolution` model
- [ ] Add tests for time parsing edge cases (relative, absolute, ambiguous)

#### Step 3: Cleanup

- [ ] Delete `src/agent/models.py` (all models: ExtractedTask, ExtractionResult, TaskStatusUpdate, ReminderTimeResolution, ToolCall, AgentDecision)
- [ ] Delete `src/agent/task_matching.py` (entire module)
- [ ] Delete `src/providers/base.py` (ModelProvider protocol)
- [ ] Delete `src/providers/gemini.py` (GeminiProvider)
- [ ] Delete `src/tools/executor.py` (ToolExecutor — Pydantic AI replaces)
- [ ] Add tool-level idempotency (same title + same day = skip)
- [ ] Add turn-level dedup (track executed tool calls within turn)

#### Step 4: Prompt Restructure

- [ ] Split system prompt: static prefix (persona, voice, rules) + dynamic suffix (current_time, task list)
- [ ] Prompt fragment registry keyed by session state (default, morning, proactive_checkin)
- [ ] Static prefix enables prompt caching (identical prefix across calls)

### 1.2 Remaining Production Tasks

- [ ] Fix `datetime.utcnow()` deprecation in `tests/fakes.py` (71 warnings) → use `datetime.now(datetime.UTC)`
- [ ] Token/cost tracking per turn (Pydantic AI + Logfire or structured logging)
- [ ] Anti-nag rules for reminders:
  - Minimum cooldown between proactive messages (45min)
  - Daily budget (max N proactive/day, configurable)
  - Response rate tracking (ignores >50% of category → halve frequency)
  - Progressive back-off (3 consecutive ignored → pause 24hrs)
  - Explicit mute-list per user/task-category (deterministic, not prompt-based)
- [ ] Deploy to Railway (always-on)
- [ ] Structured observability: latency, token counts, tool call success/failure (Logfire or OTel)
- [ ] Proactive check-ins (Phase 1 prep):
  - Cron-triggered evening check-in
  - New session with `session_type="proactive_checkin"`
  - Anti-nag rules decide: create, attach, defer, or skip

### 1.3 User Dashboard

Simple web dashboard for user onboarding and self-service. Not a full app — a lightweight admin/settings page.

- [ ] Tech: Next.js or simple HTML + Supabase Auth
- [ ] Features:
  - User registration / Telegram linking (generate a pairing code)
  - Profile settings (name, timezone, wake/sleep time, session timeout)
  - Task history view (today, this week)
  - Reminder preferences (categories to mute, daily budget)
  - Data export / delete (GDPR-ready)
  - Feedback history
- [ ] Auth: Supabase Auth (email/magic link or Telegram Login Widget)
- [ ] Hosting: same Railway project or Vercel

### Tech Stack (Phase 1)

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI (Python 3.12+) |
| **LLM** | Gemini 2.5 Flash via Pydantic AI |
| **Agent** | `pydantic-ai` Agent with native tool calling |
| **Database** | Supabase (PostgreSQL + RLS) |
| **Scheduler** | APScheduler in-memory + Supabase reload on startup |
| **Interface** | Telegram Bot API + CLI (dev) |
| **Dashboard** | Next.js or static HTML + Supabase Auth |
| **Observability** | Logfire (Pydantic AI integration) |
| **Time Parsing** | `dateparser` + category-aware rules |

---

## Phase 2 — Memory Evolution + Virtual Friend + Voice

Advanced features after Phase 1 is stable and dogfooded.

### 2.1 Memory Evolution

- [ ] User facts table — short key/value entries ("skips gym on Mondays", "dentist next Tuesday")
- [ ] Nightly summarization job: reviews day's sessions, writes facts
- [ ] Implicit feedback tracking: snooze rate, completion rate by time-of-day, reminder phrasing effectiveness
- [ ] Feed patterns back into personalization ("you complete tasks faster with 30min reminders")
- [ ] pgvector semantic search for long-term recall (when structured facts aren't enough)
- [ ] Graphiti temporal knowledge graph + Neo4j Aura (if needed beyond pgvector)
- [ ] Sleep-time agent for memory consolidation
- [ ] Memory Inspector in dashboard:
  - View all learned facts, routines, known people
  - "🗑️ Forget this" per item
  - "Pause Learning" toggle

### 2.2 Virtual Friend + Voice

- [ ] Proactive conversation engine (check-ins, emotional awareness)
- [ ] Meal/hydration reminders with full anti-nag
- [ ] Coaching style adaptation (5-axis, signal-driven):
  - Warmth, Directiveness, Challenge, Verbosity, Emotional Depth
  - Explicit signals ("be more direct") + implicit (ignores long messages)
  - Temporal shifting (casual morning, focused afternoon, reflective evening)
- [ ] Model routing: Flash by default, `escalate_to_pro` tool for emotional nuance
- [ ] Voice: Gemini Live API (primary) + Whisper/ElevenLabs (fallback)
  - `VoiceProvider` abstraction
- [ ] Mobile app (Flutter or React Native — decide based on Phase 1 learnings)
- [ ] PACT evaluation (Presence, Authenticity, Continuity, Traction — LLM-as-Judge per session)
- [ ] Evals: golden-set trajectories for tool-calling loops (right tools, right order, right args)

---

## Verification Plan

### Automated Tests
- All existing 62 tests (agent planning, allowlist, channels, onboarding, reminders, scheduler, sessions, timezone, tools, turns)
- New: tool-calling loop trajectory tests (multi-intent, tool chaining, error recovery)
- New: deterministic time parsing (relative, absolute, ambiguous, category-aware)
- New: tool idempotency (duplicate create_task within turn)
- New: anti-nag rule enforcement

### Dogfooding Protocol
- Use Amigo daily
- `/feedback` captures friction points in real-time
- Weekly review of feedback entries
- Cold-start test: reset profile, re-onboard, verify graceful degradation
- Nagging test: ignore 3 days → verify back-off
- Memory test (Phase 2): share 10 facts across 5 sessions → verify recall

---

## Key References

| Paper / Tool | Relevance |
|-------------|-----------|
| [Pydantic AI](https://ai.pydantic.dev/) | Agent framework with native tool calling |
| [Generative Agents (Stanford, 2023)](https://arxiv.org/abs/2304.03442) | Observe → Plan → Reflect agent loop |
| [Zep/Graphiti](https://github.com/getzep/graphiti) | Temporal knowledge graph for Phase 2 memory |
| [MemGPT / Letta](https://arxiv.org/abs/2310.08560) | Three-tier memory architecture pattern |
| [Gemini Live API](https://ai.google.dev/gemini-api/docs/live) | Real-time voice with affective dialog |
| [Logfire](https://logfire.pydantic.dev/) | Observability for Pydantic AI agents |
