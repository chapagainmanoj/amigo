# Amigo — Your AI Virtual Friend

A Telegram bot that helps you plan your day, sends gentle reminders, and evolves into a proactive virtual friend.

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Set up environment
cp .env.example .env
# Edit .env with your keys (Telegram, Supabase, Google AI)

# 4. Run Supabase migration
# Copy migrations/001_initial_schema.sql into your Supabase SQL editor

# 5. Start ngrok tunnel
ngrok http 8000

# 6. Update .env with ngrok URL
# APP_BASE_URL=https://your-subdomain.ngrok-free.app

# 7. Run the app
uvicorn src.main:app --reload --port 8000
```

## Commands

- Just talk to Amigo — it'll figure out what you need
- `/feedback your thoughts here` — capture friction points for weekly review

## Architecture

```
src/
├── main.py          # FastAPI + Telegram webhook
├── config.py        # Environment settings
├── agent/           # LLM logic (prompts, task extraction, conversation)
├── bot/             # Telegram handlers, onboarding, keyboards
├── channels/        # MessageChannel abstraction (Telegram, WhatsApp later)
├── providers/       # ModelProvider abstraction (Gemini, Claude later)
├── memory/          # Supabase CRUD, session boundaries, context assembly
├── scheduler/       # APScheduler reminder management
└── db/              # Supabase client
```

See [implementation_plan.md](implementation_plan.md) for full design docs.
