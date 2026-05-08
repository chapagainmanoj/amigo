# Amigo — Your AI Virtual Friend

A Telegram bot that helps you plan your day, sends gentle reminders, and evolves into a proactive virtual friend.

## What Works In Phase 1a

- Three-step Telegram onboarding: name, timezone, first planning prompt
- Allowlisted access for private dogfooding
- Natural-language task extraction with Gemini Flash
- Reminder scheduling with Done/Skip/Later buttons
- Text status updates like "done with slides" or "skip gym"
- Pending reminder reload after app restart
- User-timezone-aware task dates, session rollover, and reminder times
- `/feedback` capture into Supabase

## Install

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Upgrade pip
python -m pip install --upgrade pip

# 3. Install Amigo and dev dependencies
pip install -e ".[dev]"
```

## Configure

```bash
cp .env.example .env
```

Edit `.env`:

```bash
TELEGRAM_BOT_TOKEN=your-bot-token-from-botfather
TELEGRAM_WEBHOOK_SECRET=generate-a-random-string
ALLOWED_TELEGRAM_CHAT_IDS=123456789

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key

GOOGLE_API_KEY=your-gemini-api-key

APP_BASE_URL=https://your-ngrok-url.ngrok-free.app
APP_ENV=development
LOG_LEVEL=INFO
```

Notes:

- Create the Telegram bot with BotFather and put its token in `TELEGRAM_BOT_TOKEN`.
- Get your Telegram chat ID from a bot like `@userinfobot`.
- Leave `ALLOWED_TELEGRAM_CHAT_IDS` empty only for local open testing.
- `TELEGRAM_WEBHOOK_SECRET` can be any strong random string.

## Set Up Supabase

1. Create a Supabase project.
2. Open the Supabase SQL editor.
3. Run [migrations/001_initial_schema.sql](migrations/001_initial_schema.sql).
4. Copy your project URL into `SUPABASE_URL`.
5. Copy your service role key into `SUPABASE_SERVICE_KEY`.

## Run Locally

Terminal 1:

```bash
ngrok http 8000
```

Copy the HTTPS ngrok URL into `.env`:

```bash
APP_BASE_URL=https://your-subdomain.ngrok-free.app
```

Terminal 2:

```bash
source .venv/bin/activate
uvicorn src.main:app --reload --port 8000
```

On startup, Amigo sets the Telegram webhook to:

```text
{APP_BASE_URL}/webhook
```

Health check:

```bash
curl http://localhost:8000/health
```

## Test And Lint

```bash
source .venv/bin/activate
python -m pytest tests/ -v
ruff check src tests
```

## Commands

- Just talk to Amigo — it'll figure out what you need
- `/feedback your thoughts here` — capture friction points for weekly review

## Architecture

```
src/
├── main.py          # FastAPI + Telegram webhook
├── config.py        # Lazy environment settings
├── agent/           # LLM logic (prompts, task extraction, conversation)
├── bot/             # Telegram adapter, onboarding, turns, reminder actions
├── channels/        # MessageChannel abstraction (Telegram, WhatsApp later)
├── providers/       # ModelProvider abstraction (Gemini, Claude later)
├── memory/          # Supabase store, sessions, context assembly
├── scheduler/       # APScheduler reminder management + reload
├── utils/           # Clock/timezone helpers
└── db/              # Supabase client
```

See [implementation_plan.md](implementation_plan.md) for full design docs.
