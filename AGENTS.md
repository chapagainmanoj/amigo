# Project Overview

Amigo is an AI accountability companion delivered through Telegram with a
paired dashboard and local CLI development mode. It extracts Tasks through
the configured Gemini model, schedules participant-requested Reminders, and
maintains Session-scoped context. The repository is in internal pre-beta
development/dogfooding; the approved first external cohort starts only after Gate B passes.

See [docs/architecture.md](docs/architecture.md) for structure, patterns,
data flow, and extensibility.

## Build & Run

```bash
# Install
pip install -e ".[dev]"

# project currently have .venv

# Run locally (CLI — no Telegram/Supabase needed)
APP_CHANNEL=cli GOOGLE_API_KEY=your-key python -m src.cli

# Run locally (Telegram)
uvicorn src.main:app --reload --port 8000

# Test
python -m pytest tests/ -v

# Lint
ruff check src tests scripts

# Smoke checks (no Supabase needed)
python scripts/smoke_check.py --scheduler
```

## Code Style

- **Python 3.12+**, line length 100, ruff rules `E,F,I,N,UP,B,SIM`.
- **Files**: `snake_case.py`. **Classes**: `PascalCase`. **Constants**:
  `UPPER_SNAKE_CASE`. **Private**: `_` prefix.
- **All methods are `async def`**, even sync-under-the-hood ones.
- **No `datetime.utcnow()`** — use `src.utils.utc_now()` or inject
  a `Clock`.

## Agent Guardrails

### Authorized build scope (22 October 2026)

- Follow the Amigo Modes build plan, phases 0, 1, 1b, 2, 3, 4, 5, 6, on `develop`.
- Migrations 017+, schema bumps, and setting evaluated Modes live are authorized.
- Protected files are editable: `src/config.py`, `migrations/*.sql`, `src/db/supabase.py`,
  `scripts/smoke_check.py`. List each edit in the phase review queue.
- Never push, deploy, apply migrations to Supabase, or edit `.env`. CBT personal input stays off.
- Stop for the owner's Phase 3 test-bot spike and after the Issue 09 threat model. Stop for
  uncovered changes to production data, secrets, or privacy promises.
- Append commits, touched/protected files, test/Ruff/Gate A evidence, provisional decisions,
  and open questions to `.scratch/modular-modes/review-queue.md` after each phase; then continue
  unless the phase requires a stop.
- Use independent subagents for the Phase 2 Store review and every migration review; use
  subagents for parallel slices. Report concrete test output and diffs only.
- Daily instructions and Tool schema stay byte-identical.
- Add newly reachable Turn modules to `INVALIDATING_INPUT_PATHS` in
  `src/evaluation/gate_a.py`; never weaken `tests/test_gate_a_currency.py`.
- Development/iteration uses `claude -p`, with `ANTHROPIC_API_KEY` removed from its environment;
  Ollama is the offline backup.
- **Billed models are locked (owner, 23 Oct 2026).** Do not run evals, tests or experiments on any
  billed provider (Gemini, OpenAI, DeepSeek, Anthropic API) unless the owner explicitly allows that
  specific run in the current conversation. Model routing is fixed: Daily on `DEFAULT_MODEL`
  (Render), Coach pinned to `google:gemini-3.8-flash`; do not change either without owner approval.
  Any approved billed run records metadata-only usage in `.scratch/gemini-usage.jsonl`.
- Claude subscription CLI is development-only. Production stays on Gemini unless an evaluated
  owner-controlled override is configured. Participant model choice/keys are deferred.
- Participant pins are only for owner/internal dogfooding accounts. Never pin real participants
  to Claude: Anthropic processing requires renewed consent under decision 04.

### Never auto-delete

- `tests/fakes.py` — shared test infrastructure
- `README.md`, `AGENTS.md`

### Boundaries

- **No Supabase queries outside `MemoryStore`** — all DB access goes
  through the store layer.
- **No Telegram imports outside `src/channels/telegram.py`** — the
  library is an implementation detail.
- **No direct side effects in `src/agent/`** — the agent classifies
  and plans; side effects go through `src/tools/` (see ADR 0001).
- **Store sync**: any change to `MemoryStore` methods must be mirrored
  in `InMemoryStore` and `FakeStore` (three implementations).
- **Protocol changes**: any change to `MessageChannel` or
  `ModelProvider` requires verifying all implementations. `MessageChannel` changes cover
  `TelegramChannel`, `CLIChannel`, `FakeChannel`, and both `FailingChannel` classes in
  `tests/test_reminders.py` and `tests/test_scheduler.py`.
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
| `ACCESS_MODE` | `open` | `closed`, `allowlist`, or `registered` (alias `invite`) in production |
| `ALLOWED_TELEGRAM_CHAT_IDS` (registered) | `""` | Full-access chats: all live Modes, no trial cap |
| `TRIAL_MESSAGE_LIMIT` | `30` | Participant messages for everyone else in registered mode |
| `TRIAL_CONTACT` | contact page | Shown when the trial finishes |
| `GUIDE_URL` | guide page | Sent by `/help` |
| `COACH_TRIAL_ENABLED` | `false` | Owner attestation that Coach readiness checks are approved |
| `ALLOWED_TELEGRAM_CHAT_IDS` | `""` | Comma-separated allowlist |
| `APP_BASE_URL` | `http://localhost:8000` | Public URL for webhooks |
| `DASHBOARD_URL` | `http://localhost:5173` | Allowed dashboard origin |
| `APP_ENV` | `development` | Environment name |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `DEFAULT_MODEL` | `gemini-3.5-flash` | LLM model identifier |
| `MODE_MODELS` / `PARTICIPANT_MODEL_PINS` | `""` | Per-Mode overrides / owner-only pins |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` | `""` | Keys, required only when routed |
| `APPROVED_MODEL_PROVIDERS` | `google` | Production processor allowlist (decision 04) |
| `SMOKE_TEST_CHAT_ID` | `""` | Chat ID for `--channel` smoke check |

## Secrets

- All secrets loaded from `.env` via `pydantic-settings` (gitignored).
- `LazySettings` defers loading so tests never need production secrets.
- CLI mode requires only `GOOGLE_API_KEY`.

## Agent skills

### Issue tracker

Issues are tracked as local Markdown files under `.scratch/`. See
`docs/agents/issue-tracker.md`.

### Triage labels

Issues use workflow-state labels plus severity labels. See
`docs/agents/triage-labels.md`.

### Domain docs

Amigo uses a single-context domain layout. See `docs/agents/domain.md`.

## Agent response style

When reporting information to me, be extremely concise and sacrifice grammar for concision.
