# Amigo — AI Virtual Friend
### Project Overview & Design Summary

---

## What Is Amigo?

Amigo is a proactive AI companion that starts as a daily task planner and evolves into a memory-rich virtual friend. Unlike AI assistants you have to query, **Amigo initiates** — it knows your routine, remembers your stories, notices when you skip lunch, and greets you when you wake up.

> "Not a chatbot you query — a friend that initiates."

---

## The Problem

Every productivity app puts the burden on the user:
- You have to open it
- You have to log your tasks
- You have to remember to check it

AI assistants are reactive. Calendar apps are rigid. Reminder apps become noise.

**Nobody has built the friend layer** — an AI that proactively reaches out at the right moment, remembers what matters to you, and adapts to how you actually live.

---

## The Solution

Amigo runs on Telegram (Phase 1), with voice and mobile coming in Phase 2.

### Core Daily Loop
```
Morning: "Hey Mano! Yesterday you had 'call mom' on your list — how'd that go? What's the plan today?"
User: "Need to finish slides, go to gym, call the client"
Amigo: schedules reminders at smart times throughout the day
2pm: "Hey — you mentioned the client call today. Good time?"
User: "Done ✅"
Amigo: cancels reminder, notes completion
```

---

## Key Differentiators

### 1. Proactive Agency
Amigo reaches out first — morning greetings, meal check-ins, task reminders — without waiting to be asked.

### 2. Anti-Nag Intelligence
The hardest problem in companion AI. Amigo knows when *not* to message:
- Per-category cooldowns (no two messages within 45 min)
- Daily message budget (configurable, default 4)
- Progressive back-off (3 ignored messages → pause that category 24hrs)
- Sentiment gating (bad mood detected → softer approach, longer wait)

### 3. Coaching Style Adaptation
Amigo adapts across 5 personality axes based on how you respond:

| Axis | Spectrum |
|------|----------|
| Warmth | Professional ↔ Casual |
| Directiveness | Suggestive ↔ Direct |
| Challenge | Gentle ↔ Pushing |
| Verbosity | Concise ↔ Conversational |
| Emotional Depth | Surface ↔ Deep |

Starts as a **supportive older sibling** — warm, accountable, never judgmental. Adapts over time.

### 4. Temporal Memory
Uses a knowledge graph (Graphiti) that understands time — so when your wake time shifts from 7am to 8am after starting a new job, Amigo updates gracefully rather than getting stuck.

### 5. Memory Inspector (Trust Primitive)
Users can see and delete everything Amigo knows about them. Full data export. "Pause Learning" toggle. Monthly memory review prompts.

---

## Persona

Amigo is a **supportive older sibling**:
- Uses your name occasionally, not every message
- References what you actually said, not generic platitudes
- Never guilt-trips ("you should have..." is banned)
- Drops topics when you're not engaging
- Notices things without making a big deal of them

Example messages:
> *"Morning! Yesterday you had 'call mom' and 'finish slides' — how'd those go? What's on the plate for today?"*

> *"Hey, it's almost 2 — you mentioned wanting to call your mom today. Good time?"*

> *"So 'finish slides' carried over from yesterday. Still on the list or should we drop it?"*

**What kind of friend Amigo could be in future?** Not in feature terms — in *personality* terms. Think of a real person:
- **The chill roommate**: Laid-back, low-pressure, "hey do your thing, I'm here if you need me"
- **The supportive older sibling**: Warm, encouraging, gently keeps you accountable but never judges
- **The sharp best friend**: Direct, calls you out (lovingly), pushes you, celebrates wins hard
- **The calm mentor**: Measured, asks good questions instead of giving answers, helps you think
The default coaching profile we designed adapts over time — but it needs a **starting personality** before it has any signals to learn from. This is what the user experiences in the onboarding conversation and first 7 days.

---

## Technical Architecture

### Phase 1 Stack (Shipping Now)
| Layer | Technology |
|-------|-----------|
| Interface | Telegram Bot |
| Backend | Python 3.12 + FastAPI |
| LLM | Gemini 2.5 Flash (routine) → Claude Sonnet (emotional) |
| Agent Framework | Pydantic AI |
| Database | Supabase (PostgreSQL + pgvector + RLS) |
| Scheduler | APScheduler (in-memory → Redis on deploy) |
| Deployment | Railway |

### Phase 2 Additions
- Graphiti temporal knowledge graph
- Gemini Live API for voice (with Whisper + ElevenLabs fallback)
- Flutter mobile app
- Full coaching style adaptation
- 12-dimension session evaluation framework

### Model Routing Strategy
- **Gemini Flash** — routine reminders, task extraction, PACT evaluation (~$0.001/day/user)
- **Claude Sonnet** — emotional conversations, onboarding, coaching calibration
- **Small local model** — memory extraction (near-zero cost)
- **Voice** — premium tier given $3-7/day cost vs $0.01/day text

---

## Session Evaluation (PACT Framework)

Every conversation is scored across 4 dimensions:

| Dimension | Measures |
|-----------|---------|
| **Presence** | Was Amigo's timing right? |
| **Authenticity** | Did it feel like a friend, not a bot? |
| **Continuity** | Did it remember the right context? |
| **Traction** | Did the session lead to action? |

Scores drive automatic system improvements — low Presence → increase cooldowns, low Continuity → improve memory retrieval.

---

## Build Plan

### Phase 1a — MVP (Week 1, shipping now)
- Telegram bot + Supabase
- Onboarding (name + timezone)
- Morning planning conversation
- Task extraction + reminders
- `/feedback` command

### Phase 1b — Intelligence (Week 3-6)
- Routine learning with confidence scoring
- Anti-nag governor
- PACT evaluation
- Coaching style initial profile

### Phase 2a — Memory (Week 7-10)
- Graphiti knowledge graph
- Sleep-time memory consolidation
- Memory Inspector UI

### Phase 2b — Voice + Friend (Week 11-14)
- Gemini Live API voice
- Proactive conversation engine
- Full coaching adaptation

---

## Unit Economics

| User Type | Daily Cost |
|-----------|-----------|
| Text-only | ~$0.01 |
| Voice-heavy | ~$3-7 |

Text users at scale are essentially free. Voice is a natural premium tier.

---

## Research Foundation

| Paper / Tool | How Amigo Uses It |
|-------------|-------------------|
| [Generative Agents (Stanford)](https://arxiv.org/abs/2304.03442) | Observe → Plan → Reflect agent loop |
| [Zep/Graphiti](https://github.com/getzep/graphiti) | Temporal memory with contradiction handling |
| [MemGPT / Letta](https://arxiv.org/abs/2310.08560) | Three-tier memory architecture |
| [Gemini Live API](https://ai.google.dev/gemini-api/docs/live) | Real-time affective voice |

---

## Current Status

Amigo is in active development. Phase 1a is being dogfooded daily by the founder. The architecture has been through a rigorous design review covering 24+ implementation questions — session boundaries, timezone handling, reminder reliability, coaching adaptation, context window management, and conversation evaluation.

**The foundation is solid. The MVP ships this week.**

---

## What Makes This Defensible

1. **The anti-nag system is hard to copy** — it requires real behavioral data and careful calibration. Easy to describe, hard to get right.

2. **Memory compounds** — the longer a user stays, the more Amigo knows, the more valuable it becomes. High switching cost after month 1.

3. **Voice + text + proactive** is a combination nobody has shipped well at this price point.

4. **Emotional attunement** — using Claude Sonnet specifically for emotional conversations produces meaningfully better output than generic models. This is a product decision most competitors won't make.

---

*Built with Python, Supabase, Gemini, and Claude. Designed for people who want a friend, not another app.*