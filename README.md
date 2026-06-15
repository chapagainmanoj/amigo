# Amigo — Your AI Virtual Friend

A Telegram bot that helps you plan your day, sends gentle reminders,
and evolves into a proactive virtual friend. Powered by Gemini Flash.

## What Can Amigo Do?

- **Plan your day** — just tell Amigo what you need to do in plain
  language and it extracts tasks, sets reminders, and checks in later.
- **Smart reminders** — get nudges at the right time with Done, Skip,
  or Later buttons. Snooze escalates so nothing falls through.
- **Status updates** — say "done with slides" or "skip gym" and Amigo
  updates your tasks automatically.
- **Morning planning** — first message of the day triggers a planning
  session that reviews yesterday's unfinished tasks.
- **Session memory** — Amigo remembers your conversation context within
  and across sessions. Say "goodnight" to close the day.
- **Feedback capture** — `/feedback your thoughts` logs friction points
  for weekly review.

## For Users

### Talking to Amigo

No special commands needed — just chat naturally:

- *"Gym at 5pm, finish slides by 3, call mom after dinner"*
- *"Done with the slides"*
- *"Skip gym today"*
- *"Goodnight"*

When a reminder fires, you'll see three buttons:

| Button | What it does |
|--------|-------------|
| **Done ✅** | Marks the task complete |
| **Skip ⏭️** | Skips the task for today |
| **Later ⏰** | Snoozes (60 min → 30 min → defers to tomorrow) |

### Commands

| Command | Purpose |
|---------|---------|
| *(just talk)* | Amigo figures out what you need |
| `/feedback ...` | Capture friction points for review |

---

## For Developers

### Prerequisites

- Python 3.12+
- A [Google AI API key](https://aistudio.google.com/apikey) (Gemini)

### Quick Start (CLI Mode)

The fastest way to develop locally. No Telegram bot, no ngrok, no
Supabase — just your Gemini key.

```bash
# 1. Clone and set up
git clone <repo-url> && cd amigo
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Run
APP_CHANNEL=cli GOOGLE_API_KEY=your-key python -m src.cli
```

This gives you an interactive terminal chat with:

- In-memory data store (no database needed, data resets on exit)
- Inline buttons rendered as numbered choices (`[1] Done  [2] Skip`)
- Live reminder scheduler — reminders fire in the terminal
- Dev user pre-seeded (skips onboarding)

CLI-only commands:

| Command | Purpose |
|---------|---------|
| `/quit` | Exit the CLI |
| `/tasks` | Dump today's tasks and statuses |
| `/debug` | Toggle debug logging on/off |

To test the full onboarding flow:

```bash
APP_CHANNEL=cli GOOGLE_API_KEY=your-key python -m src.cli --onboard
```

### Full Setup (Telegram Mode)

Required for production or end-to-end Telegram testing.

#### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
# Google AI (required for all modes)
GOOGLE_API_KEY=your-gemini-api-key

# Telegram
TELEGRAM_BOT_TOKEN=your-bot-token-from-botfather
TELEGRAM_WEBHOOK_SECRET=generate-a-random-string
ALLOWED_TELEGRAM_CHAT_IDS=123456789

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key

# App
APP_BASE_URL=https://your-ngrok-url.ngrok-free.app
```

Where to get these:

- **Telegram bot token** — create a bot with
  [@BotFather](https://t.me/BotFather) on Telegram.
- **Your chat ID** — message [@userinfobot](https://t.me/userinfobot)
  on Telegram to get your numeric chat ID.
- **Webhook secret** — any strong random string (e.g., `openssl rand
  -hex 32`).
- **Supabase** — create a project at
  [supabase.com](https://supabase.com), copy URL and service role key.

#### 2. Set up the database

1. Create a Supabase project.
2. Open the SQL editor in the Supabase dashboard.
3. Run [`migrations/001_initial_schema.sql`](migrations/001_initial_schema.sql).

#### 3. Run

```bash
# Terminal 1 — expose local server to the internet
ngrok http 8000

# Copy the HTTPS URL into .env as APP_BASE_URL

# Terminal 2 — start Amigo
source .venv/bin/activate
uvicorn src.main:app --reload --port 8000
```

On startup, Amigo registers its Telegram webhook at
`{APP_BASE_URL}/webhook`.

Health check: `curl http://localhost:8000/health`

### Test & Lint

```bash
python -m pytest tests/ -v         # 62 unit tests, no network needed
ruff check src tests scripts       # lint
```

All tests use in-memory fakes — no Supabase, Telegram, or Gemini
calls. See [`tests/fakes.py`](tests/fakes.py) for the shared test
doubles.

### Smoke Checks

The [`scripts/smoke_check.py`](scripts/smoke_check.py) script runs
production-liveness checks without touching Supabase:

```bash
# In-memory scheduler — proves APScheduler fires through the channel
python scripts/smoke_check.py --scheduler

# Real Telegram ping — sends one message to verify delivery
TELEGRAM_BOT_TOKEN=... SMOKE_TEST_CHAT_ID=... python scripts/smoke_check.py --channel

# Both checks
python scripts/smoke_check.py --all
```

### Environment Variables

| Variable | Default | Required for |
|----------|---------|-------------|
| `APP_CHANNEL` | `telegram` | — (set to `cli` for CLI mode) |
| `GOOGLE_API_KEY` | — | All modes |
| `TELEGRAM_BOT_TOKEN` | `""` | Telegram mode |
| `TELEGRAM_WEBHOOK_SECRET` | `""` | Telegram mode |
| `SUPABASE_URL` | `""` | Telegram mode |
| `SUPABASE_SERVICE_KEY` | `""` | Telegram mode |
| `ALLOWED_TELEGRAM_CHAT_IDS` | `""` | Telegram mode (empty = allow all) |
| `APP_BASE_URL` | `localhost:8000` | Telegram mode |
| `APP_ENV` | `development` | — |
| `LOG_LEVEL` | `INFO` | — |
| `DEFAULT_MODEL` | `gemini-2.5-flash` | — |
| `SMOKE_TEST_CHAT_ID` | — | Smoke checks (`--channel`) |

### Deploy to Production (Fly.io)

Amigo deploys as one always-on Fly.io Machine. Keep production scaled to
one Machine while reminders run inside the FastAPI process.

#### 1. Create the Fly app

```bash
fly launch --no-deploy
```

If Fly creates a different app name, update `app` and `APP_BASE_URL` in
`fly.toml`.

#### 2. Set production secrets

```bash
fly secrets set \
  GOOGLE_API_KEY=your-gemini-api-key \
  TELEGRAM_BOT_TOKEN=your-bot-token \
  TELEGRAM_WEBHOOK_SECRET=your-strong-random-secret \
  ALLOWED_TELEGRAM_CHAT_IDS=your-chat-id \
  SUPABASE_URL=https://your-project.supabase.co \
  SUPABASE_SERVICE_KEY=your-service-role-key
```

Non-secret production config lives in `fly.toml`.

#### 3. Deploy manually

```bash
fly deploy --remote-only
```

Or use the GitHub Actions `Deploy` workflow. It runs tests first, waits
for approval in the `production` environment, then deploys with
`FLY_API_TOKEN`.

#### 4. Configure GitHub production deploys

1. Create a GitHub environment named `production`.
2. Add an environment secret named `FLY_API_TOKEN`.
3. Require manual approval for the `production` environment.

Create the token with:

```bash
fly tokens create deploy -x 999999h
```

#### 5. Verify

```bash
curl https://amigo.fly.dev/health
fly logs
```

On startup, Amigo automatically registers the Telegram webhook at
`{APP_BASE_URL}/webhook`. Send a message to your bot on Telegram to
confirm everything works.

### Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full picture:
repository structure, design patterns, data flow diagram, key
abstractions, extensibility hooks, and testing strategy.

### What Works in Phase 1a

- Three-step Telegram onboarding: name, timezone, first planning prompt
- Local CLI mode for development (no external services needed)
- Natural-language task extraction with Gemini Flash
- Structured agent planning with tool-based side effects (ADR 0001)
- Reminder scheduling with Done/Skip/Later buttons
- Text status updates ("done with slides", "skip gym")
- Pending reminder reload after app restart
- User-timezone-aware task dates, session rollover, and reminder times
- `/feedback` capture into Supabase
- Allowlisted access for private dogfooding
- Production smoke checks (scheduler + Telegram channel liveness)
