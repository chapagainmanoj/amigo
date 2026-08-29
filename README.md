# Amigo — AI Accountability Companion

Tell Amigo what you need to do in a Telegram conversation. It creates Tasks and sends Reminders
at the time you choose, with simple Done, Skip, and Later controls. A paired web dashboard shows
the current prototype state.

Amigo is in invitation-only beta development. See the
[capability matrix](docs/capability-matrix.md) before describing, demonstrating, or deploying it.

## What Can Amigo Do?

- **Capture tasks conversationally** — tell Amigo what you need to do in plain language and it
  creates Tasks, optionally with a time you choose.
- **Receive Telegram reminders** — a scheduled Reminder includes Done, Skip, and Later buttons.
- **Status updates** — say "done with slides" or "skip gym" and Amigo
  updates your tasks automatically.
- **Continue recent context** — Amigo uses the current Session, recent Task context, and a recent
  Session summary. This is not durable personal Memory.
- **Review the prototype dashboard** — after pairing Telegram, view and edit current Tasks and see
  pending Reminders and recent Sessions. Cross-surface consistency is still release-gated.
- **Feedback capture** — `/feedback your thoughts` logs friction points
  for weekly review.

Amigo does not currently provide autonomous morning/evening check-ins, a Memory Inspector,
adaptive coaching Modes, wellbeing treatment, WhatsApp, voice, or native mobile apps.

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
git clone https://github.com/chapagainmanoj/amigo.git && cd amigo
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
4. Run [`migrations/002_auth_linking_and_rls.sql`](migrations/002_auth_linking_and_rls.sql).

Apply migrations in numeric order. The second migration is required for dashboard pairing and
row-level access control.

#### 3. Run

```bash
# Terminal 1 — expose local server to the internet
ngrok http 8000

## copy command from ngrok dashboard to update the webhook url for telegram

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
python -m pytest tests/ -v         # 69 unit tests at the latest capability review
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

### Deployment Status

Render is the canonical beta deployment target, described by [`render.yaml`](render.yaml). The
invitation beta must use one always-on service and one scheduler owner; a sleeping free instance
is suitable only for development. `fly.toml` and the Fly workflow are retained as inactive future
deployment material and are not a second production path.

The repository does not yet provide a supported self-hosting product. Before a real deployment,
follow the security, staging, monitoring, backup, and end-to-end gates in the
[pre-launch implementation plan](docs/pre-launch-implementation-plan.md).

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

This list describes repository behavior, not proof that the external services work together in
production. See the [capability matrix](docs/capability-matrix.md) for current limits and roadmap
separation.

## Contributing and Security

Contributions require Developer Certificate of Origin 1.1 sign-off. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, checks, and submission guidance. Report suspected
vulnerabilities privately as described in [`SECURITY.md`](SECURITY.md); do not publish unpatched
details in an issue.

## License

Amigo's original source code, scripts, and documentation are licensed under the
[GNU Affero General Public License version 3](LICENSE). Identified third-party materials retain
their applicable licenses and rights. The open-source license permits independent deployment but
does not promise official support for self-hosted installations.
