# Project Overview

Amigo is an AI virtual friend delivered as a Telegram bot (with a local
CLI mode for dev). It extracts tasks from natural language via Gemini
Flash, schedules reminders with snooze logic, and maintains session-aware
context. Phase 1a — single-user dogfooding.

See [docs/architecture.md](docs/architecture.md) for structure, patterns,
data flow, and extensibility.

## Build & Run

```bash
# Install
pip install -e ".[dev]"

# Run locally (CLI — no Telegram/Supabase needed)
APP_CHANNEL=cli GOOGLE_API_KEY=your-key python -m src.cli

# Run locally (Telegram)
uvicorn src.main:app --reload --port 8000

# Test
python -m pytest tests/ -v

# Lint
ruff check src tests
```

## Code Style

- **Python 3.12+**, line length 100, ruff rules `E,F,I,N,UP,B,SIM`.
- **Files**: `snake_case.py`. **Classes**: `PascalCase`. **Constants**:
  `UPPER_SNAKE_CASE`. **Private**: `_` prefix.
- **All methods are `async def`**, even sync-under-the-hood ones.
- **No `datetime.utcnow()`** — use `src.utils.utc_now()` or inject
  a `Clock`.

## Agent Guardrails

### Never modify without human review

- `.env` — production secrets
- `migrations/*.sql` — schema changes affect production data
- `src/config.py` — changing defaults can break all environments
- `src/db/supabase.py` — singleton wiring

### Never auto-delete

- `tests/fakes.py` — shared test infrastructure
- `README.md`, `AGENTS.md`

### Boundaries

- **No Supabase queries outside `MemoryStore`** — all DB access goes
  through the store layer.
- **No Telegram imports outside `src/channels/telegram.py`** — the
  library is an implementation detail.
- **Store sync**: any change to `MemoryStore` methods must be mirrored
  in `InMemoryStore` and `FakeStore` (three implementations).
- **Protocol changes**: any change to `MessageChannel` or
  `ModelProvider` requires verifying all implementations.
- **Rate limits**: Gemini retries once then returns an error message.
  Do not add aggressive retry loops.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_CHANNEL` | `telegram` | `"cli"` for local dev |
| `GOOGLE_API_KEY` | (required) | Gemini API key |
| `TELEGRAM_BOT_TOKEN` | `""` | Telegram bot token |
| `TELEGRAM_WEBHOOK_SECRET` | `""` | Webhook auth secret |
| `SUPABASE_URL` | `""` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | `""` | Supabase service role key |
| `ALLOWED_TELEGRAM_CHAT_IDS` | `""` | Comma-separated allowlist |
| `APP_BASE_URL` | `http://localhost:8000` | Public URL for webhooks |
| `APP_ENV` | `development` | Environment name |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `DEFAULT_MODEL` | `gemini-2.5-flash` | LLM model identifier |

## Secrets

- All secrets loaded from `.env` via `pydantic-settings` (gitignored).
- `LazySettings` defers loading so tests never need production secrets.
- CLI mode requires only `GOOGLE_API_KEY`.
