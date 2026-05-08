# Amigo — Implementation Plan

An AI companion that acts as a proactive virtual friend: plans your day, sends reminders, and evolves into a memory-rich conversational partner.

---

## Resolved Decisions

All architectural decisions resolved via design review. No open questions remain for Phase 1.

| # | Decision | Resolution |
|---|----------|------------|
| 1 | Multi-tenancy | Single-user, tenant-aware schemas (`user_id` + RLS from day one) |
| 2 | Primary interface | Telegram bot (primary) + WhatsApp (secondary), `MessageChannel` abstraction |
| 3 | Mobile app | Deferred — validate with Telegram first, decide Flutter vs RN later |
| 4 | Model routing | Gemini Flash for everything in Phase 1. Sonnet for emotional, local for extraction in Phase 2 |
| 5 | Agent framework | Raw Python + Pydantic AI for Phase 1. Evaluate LangGraph/ADK for Phase 2 |
| 6 | Morning greeting | Reactive in Phase 1a: first local-day message is routed to morning planning. Adaptive proactive in Phase 1b |
| 7 | Evening reflection | No proactive push. Morning conversation surfaces yesterday's tasks naturally |
| 8 | Database | Supabase-only (Postgres + pgvector + RLS) for Phase 1. Graphiti + Neo4j Aura in Phase 2a |
| 9 | Deployment | Local Mac + ngrok for dev. Railway when ready for always-on |
| 10 | Language | English-first, tolerates Nepali/Hindi code-switching input |
| 11 | Task model | Dateless "today's list" with optional `due_date` column. App sets `created_date` from the user's timezone. No automated rollover |
| 12 | Session boundaries | Type-aware + user-timezone-aware. 2hr configurable inactivity gap. Local midnight hard-close |
| 13 | Persona | Supportive older sibling. Voice over adjectives. 3 example messages in system prompt |
| 14 | Corrections | Brief "Updated ✓" confirmations. Silent behavioral adaptation. Explicit commands as tool calls |
| 15 | LLM abstraction | `ModelProvider` interface — no hard dependency on any single provider |
| 16 | MVP scope | Telegram bot + allowlisted access + tasks + reminders + text/button status updates + `/feedback`. Nothing else |
| 17 | Telegram formatting | Plain text by default. No Markdown parse mode until escaping is implemented |
| 18 | Reminder persistence | APScheduler in memory, with pending reminder reload from Supabase on startup and a missed-fire grace window |

---

## Phase 1a MVP — Ship in 1 Week

### What Gets Built

| In (Phase 1a) | Out (Phase 1b+) |
|----------------|-----------------|
| Telegram bot that responds to messages | WhatsApp, mobile app |
| Onboarding conversation (name, timezone) | Wake/sleep routine capture, full coaching style calibration |
| "What are you doing today?" → extracts task list | Smart time suggestions |
| Stores tasks in Supabase | Knowledge graph, Graphiti |
| Sends reminders at user-specified times, reloads pending reminders after restart | Learned optimal times |
| Marks tasks done/skipped/deferred via buttons or text | PACT evaluation |
| Morning conversation surfaces yesterday's tasks | Automated rollover logic |
| `/feedback` command (instant capture → Supabase) | Evaluation framework |
| Gemini Flash for everything | Multi-model routing |
| Single system prompt with 3 example messages | Coaching adaptation |

### Core Loop

```
User sends first message of the day
  → Amigo greets, asks about yesterday's open tasks
  → "What are you planning to do today?"
  → User describes tasks (natural language)
  → Amigo extracts tasks, confirms, asks for reminder times
  → Schedules Telegram reminders via APScheduler
  → Throughout the day: reminder → user replies "done"/"skip"/"later"
  → User can message anytime for updates
```

### Tech Stack (Phase 1a)

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI (Python 3.12+) |
| **LLM** | Gemini 2.5 Flash via `google-genai` SDK |
| **LLM Orchestration** | `google-genai` structured outputs + Pydantic models |
| **Database** | Supabase (PostgreSQL + RLS) |
| **Scheduler** | APScheduler in-memory + Supabase reload on startup. Redis deferred |
| **Interface** | Telegram Bot API (python-telegram-bot) |
| **Dev Tunnel** | ngrok (Telegram webhooks to localhost) |

### Supabase Schema (Phase 1a)

```sql
-- Tenant-aware from day one

CREATE TABLE user_profiles (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id BIGINT UNIQUE NOT NULL,
    name TEXT,
    timezone TEXT,                          -- NULL until set in onboarding; no silent defaults
    wake_time TIME DEFAULT '07:30',
    sleep_time TIME DEFAULT '23:00',
    session_timeout_minutes INT DEFAULT 120,
    daily_message_budget INT DEFAULT 4,
    preferences JSONB DEFAULT '{}',
    coaching_profile JSONB DEFAULT '{"warmth":0.7,"directiveness":0.4,"challenge":0.4,"verbosity":0.5,"emotional_depth":0.5}',
    onboarding_complete BOOLEAN DEFAULT FALSE,
    onboarding_step INT DEFAULT 0,         -- 0=not started, 1=name, 2=timezone, 3=done
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TYPE task_category AS ENUM ('health', 'work', 'personal', 'social', 'other');
CREATE TYPE task_status AS ENUM ('pending', 'done', 'skipped', 'deferred');

CREATE TABLE tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(user_id),
    title TEXT NOT NULL,
    category task_category DEFAULT 'other', -- Enforced via Postgres enum
    due_date DATE,                         -- Optional, for Phase 1b deadline awareness
    suggested_time TIMESTAMPTZ,
    actual_completion TIMESTAMPTZ,
    status task_status DEFAULT 'pending',
    deferred_count INT DEFAULT 0,          -- 3+ → Amigo suggests dropping
    source_session_id UUID,
    created_date DATE DEFAULT CURRENT_DATE, -- App sets this in the user's timezone
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE reminders (
    reminder_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(task_id),
    user_id UUID REFERENCES user_profiles(user_id),
    scheduled_time TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'pending',         -- "pending", "sent", "acknowledged", "snoozed"
    snooze_count INT DEFAULT 0,
    telegram_message_id BIGINT,            -- For editing message to remove inline keyboard
    follow_up_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(user_id),
    session_type TEXT,                     -- "morning_planning", "check_in", "task_update", "casual"
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ DEFAULT now(), -- Updated on every message; used for timeout checks
    context_summary TEXT,                  -- Lightweight summary, not full transcript
    message_count INT DEFAULT 0
);

CREATE TABLE messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(session_id),
    user_id UUID REFERENCES user_profiles(user_id),
    role TEXT NOT NULL,                    -- "user", "assistant"
    content TEXT NOT NULL,
    channel TEXT DEFAULT 'telegram',       -- "telegram", "whatsapp", "app"
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE feedback (
    feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(user_id),
    session_id UUID REFERENCES sessions(session_id),
    content TEXT NOT NULL,
    reviewed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(user_id),
    model TEXT NOT NULL,                   -- "gemini-2.5-flash", "claude-sonnet", etc.
    input_tokens INT,
    output_tokens INT,
    estimated_cost NUMERIC(10,6),
    session_id UUID REFERENCES sessions(session_id),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- RLS policies (tenant isolation)
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
```

### System Prompt Design

Written as *how Amigo thinks*, not adjective lists:

```
You are Amigo — a friend who helps [USER_NAME] stay on track with their day.

You think of [USER_NAME] the way a supportive older sibling would: you genuinely
care about their wellbeing, you remember what they tell you, and you keep them
accountable without making them feel bad. You notice things without making a big
deal of them.

You use [USER_NAME]'s name occasionally — not every message. You reference what
they actually said, not generic platitudes. When they skip a task, you don't
guilt-trip — you're curious about what happened and help them adjust.

The user may mix English with Nepali or Hindi. Understand mixed-language input
but respond in English unless asked otherwise.

=== HOW YOU SOUND ===

Morning greeting:
"Morning [USER_NAME]! Yesterday you had 'call mom' and 'finish slides' on
your list — how'd those go? And what's on the plate for today?"

Task reminder:
"Hey, it's almost 2 — you mentioned wanting to call your mom today. Good time?"

Missed task check-in (next morning):
"So 'finish slides' carried over from yesterday. Still on the list or should
we drop it?"

=== RULES ===
- Keep messages short. 1-3 sentences for reminders. Longer only for planning.
- Never guilt-trip. Never use phrases like "you should have" or "you failed to."
- When the user corrects a fact, confirm briefly: "Updated ✓"
- If the user says "stop reminding me about X", immediately disable that reminder
  category. Confirm: "Done — won't bring it up again."
- Extract tasks from natural conversation. Confirm what you extracted.
- Suggest reminder times but let the user override.
```

### Project Structure

```
amigo/
├── implementation_plan.md
├── README.md
├── pyproject.toml
├── .env.example
├── src/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app + Telegram webhook
│   ├── config.py                  # Settings via pydantic-settings
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── handlers.py            # Thin Telegram adapter: allowlist + onboarding + turn/callback delegation
│   │   ├── keyboards.py           # Inline keyboards (Done/Skip/Later)
│   │   ├── onboarding.py          # Three-step onboarding state machine (name + timezone)
│   │   ├── reminder_actions.py    # Reminder scheduling + Done/Skip/Later callback actions
│   │   ├── task_matching.py       # Task-list and task-title matching heuristics
│   │   └── turns.py               # Authenticated message routing pipeline
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── amigo.py               # Core agent logic (conversation + task extraction)
│   │   ├── prompts.py             # System prompt + few-shot examples
│   │   └── models.py              # Pydantic models for structured LLM output
│   ├── channels/
│   │   ├── __init__.py
│   │   ├── base.py                # MessageChannel protocol
│   │   ├── telegram.py            # Telegram implementation
│   │   └── whatsapp.py            # WhatsApp implementation (Phase 1b)
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                # ModelProvider protocol
│   │   ├── gemini.py              # Gemini Flash implementation
│   │   └── anthropic.py           # Claude Sonnet implementation (Phase 2)
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── store.py               # Supabase CRUD/query module for tasks, sessions, reminders, messages
│   │   ├── sessions.py            # Session boundary logic (type-aware + time-aware)
│   │   └── context.py             # Assembles LLM context: today's tasks + current session
│   │                              #   messages + yesterday's summary + coaching profile +
│   │                              #   user name/timezone. Most perf-sensitive path.
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── reminders.py           # APScheduler reminder management + pending reload
│   ├── utils/
│   │   └── __init__.py            # Clock/timezone helpers and local-day UTC ranges
│   └── db/
│       ├── __init__.py
│       └── supabase.py            # Supabase client singleton
├── migrations/
│   └── 001_initial_schema.sql     # The schema above
└── tests/
    ├── test_task_extraction.py    # Golden cases: comma lists, vague goals ("work on
    │                              #   presentation"), time-embedded ("call mom at 3"),
    │                              #   multi-language input, single task, empty input
    ├── test_session_boundaries.py
    └── test_reminders.py
```

### Abstractions (Future-Proofing)

```python
# channels/base.py
from typing import Protocol

class MessageChannel(Protocol):
    async def send_message(self, chat_id: str, text: str, buttons: list | None = None) -> None: ...
    async def send_reminder(self, chat_id: str, task: Task) -> None: ...

# providers/base.py
class ModelProvider(Protocol):
    async def generate(self, messages: list[dict], system: str, schema: type | None = None) -> str | dict: ...

# Usage — agent doesn't know which channel or model it's using
class AmigoAgent:
    def __init__(self, model: ModelProvider, channel: MessageChannel, memory: MemoryStore):
        self.model = model
        self.channel = channel
        self.memory = memory
```

---

## Phase 1b — Intelligence (Week 3-6)

- [ ] WhatsApp channel via `MessageChannel` adapter
- [ ] Routine learning with confidence scoring (5+ observations before acting)
- [ ] Adaptive proactive morning greeting (70th percentile wake time)
- [ ] Smart time suggestions based on learned patterns
- [ ] Anti-nag governor (basic rules: cooldown, daily budget, progressive back-off)
- [ ] PACT evaluation (4 dimensions, LLM-as-Judge, per-session)
- [ ] Coaching style initial profile from onboarding signals
- [ ] Optional evening nudge (only on engaged days)
- [ ] Deadline-aware task escalation

### Cold-Start Strategy (Built into Phase 1a onboarding, refined in 1b)

| Memory Age | Behavior |
|-----------|----------|
| **Day 1-3** | Use onboarding answers + sensible defaults. Ask before assuming |
| **Day 4-7** | Tentative suggestions: "It seems like you usually..." |
| **Week 2+** | Confident routine model. Proactive nudges |
| **Month 1+** | Full temporal reasoning (Phase 2) |

### Confidence Scoring

```python
class LearnedBehavior:
    pattern: str              # e.g., "wake_time_weekday"
    value: Any
    observation_count: int
    consistency: float        # 0-1, std deviation based
    
    @property
    def confidence(self) -> float:
        if self.observation_count < 3:
            return 0.1
        base = min(self.observation_count / 10, 1.0)
        return base * self.consistency
```

### Anti-Nag Governor Rules

| Rule | Implementation |
|------|---------------|
| **Minimum Cooldown** | No two proactive messages within 45 minutes |
| **Daily Budget** | Max N proactive messages/day (user-configurable, default 4) |
| **Response Rate Tracking** | Ignores >50% of a category → halve frequency |
| **Category Spacing** | Same category max 3x/day, min 3hrs apart |
| **Progressive Back-off** | 3 consecutive ignored → pause category 24hrs |
| **Explicit Override** | "Stop reminding me about X" → tool call → permanent disable |

### PACT Evaluation (Phase 1b)

| Dimension | Measures | Score |
|-----------|----------|-------|
| **Presence** | Was the interaction well-timed? | 0-5 |
| **Authenticity** | Did it feel like a friend, not a bot? | 0-5 |
| **Continuity** | Did it remember relevant context? | 0-5 |
| **Traction** | Did the session lead to action? | 0-5 |

Single LLM-as-Judge call per session. ~50 tokens. Negligible cost.

---

## Phase 2a — Memory Evolution (Week 7-10)

- [ ] Graphiti temporal knowledge graph + Neo4j Aura Free
- [ ] Sleep-time agent for memory consolidation (runs at session close)
- [ ] Cross-session context synthesis
- [ ] Memory Inspector UI (Next.js dashboard)
  - View all learned facts, routines, known people
  - "🗑️ Forget this" per item
  - "Pause Learning" toggle
  - Export/delete all data
- [ ] Routine change detection
- [ ] Multi-model routing: Sonnet for emotional, Flash for routine
- [ ] Ollama on VPS for memory extraction

---

## Phase 2b — Virtual Friend + Voice (Week 11-14)

- [ ] Proactive conversation engine (check-ins, emotional awareness)
- [ ] Meal/hydration reminders with full anti-nag
- [ ] Full coaching style adaptation (5-axis, signal-driven)
  - Warmth, Directiveness, Challenge, Verbosity, Emotional Depth
  - Explicit signals ("be more direct") + implicit (ignores long messages)
  - Temporal shifting (casual morning, focused afternoon, reflective evening)
- [ ] Voice: Gemini Live API (primary) + Whisper/ElevenLabs (fallback)
  - `VoiceProvider` abstraction
- [ ] Mobile app (Flutter or React Native — decide based on Phase 1 learnings)
- [ ] Expand to 12-dimension evaluation (config-driven weights)

---

## Verification Plan

### Automated Tests
- Onboarding state machine (name, timezone confirm/manual/alias/invalid, completion)
- Allowlist blocks unknown chats before DB/model calls
- Timezone helpers and app-set task `created_date`
- Session boundary logic (time gaps, first local-day session, local midnight close)
- Reminder scheduling, reload, delivery guards, and status-update cancellation
- Task extraction from natural language (golden inputs → expected tasks)
- Anti-nag governor rules (Phase 1b)

### Dogfooding Protocol
- Use Amigo daily from Phase 1a ship
- `/feedback` captures friction points in real-time
- Weekly review of feedback entries
- Cold-start test: reset profile, re-onboard, verify graceful degradation
- Nagging test (Phase 1b): ignore 3 days → verify back-off
- Memory test (Phase 2a): share 10 facts across 5 sessions → verify recall

---

## Key Research References

| Paper / Tool | Relevance |
|-------------|-----------|
| [Generative Agents (Stanford, 2023)](https://arxiv.org/abs/2304.03442) | Observe → Plan → Reflect agent loop |
| [Zep/Graphiti](https://github.com/getzep/graphiti) | Temporal knowledge graph for Phase 2 memory |
| [MemGPT / Letta](https://arxiv.org/abs/2310.08560) | Three-tier memory architecture pattern |
| [Gemini Live API](https://ai.google.dev/gemini-api/docs/live) | Real-time voice with affective dialog |
