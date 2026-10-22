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
| **Later ⏰** | Uses the canonical +60 min → +30 min → next local planning day replacement lifecycle; staging evidence is still release-gated |

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
- Dev user pre-seeded (skips the CLI-only setup flow)

CLI-only commands:

| Command | Purpose |
|---------|---------|
| `/quit` | Exit the CLI |
| `/tasks` | Dump today's tasks and statuses |
| `/debug` | Toggle debug logging on/off |

To test the legacy CLI-only setup flow (the beta Activation journey is dashboard-first):

```bash
APP_CHANNEL=cli GOOGLE_API_KEY=your-key python -m src.cli --onboard
```

### Full Setup (Telegram Mode)

Required for local or deployed Telegram testing. This setup is not by itself production- or
beta-ready; the release gates below still apply.

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
ACCESS_MODE=open
ALLOWED_TELEGRAM_CHAT_IDS=123456789

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key

# App
APP_BASE_URL=https://your-tunnel-url  # optional with scripts/dev_tunnel.sh
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
5. Run [`migrations/003_secure_pairing_tokens.sql`](migrations/003_secure_pairing_tokens.sql).
6. Run [`migrations/004_tenant_isolation_policies.sql`](migrations/004_tenant_isolation_policies.sql).
7. Run [`migrations/005_canonical_task_command.sql`](migrations/005_canonical_task_command.sql).
8. Run [`migrations/006_durable_reminder_outbox.sql`](migrations/006_durable_reminder_outbox.sql).
9. Run [`migrations/007_consistent_task_reminder_resolution.sql`](migrations/007_consistent_task_reminder_resolution.sql).
10. Run [`migrations/008_atomic_later_command.sql`](migrations/008_atomic_later_command.sql).
11. Run [`migrations/009_telegram_update_claims.sql`](migrations/009_telegram_update_claims.sql).
12. Run [`migrations/010_consistent_dashboard_snapshot.sql`](migrations/010_consistent_dashboard_snapshot.sql).
13. Run [`migrations/011_reminder_reliability_instrumentation.sql`](migrations/011_reminder_reliability_instrumentation.sql).
14. Run [`migrations/012_canonical_planning_day_move.sql`](migrations/012_canonical_planning_day_move.sql).
15. Run [`migrations/013_dashboard_first_activation.sql`](migrations/013_dashboard_first_activation.sql).
16. Run [`migrations/014_application_schema_version.sql`](migrations/014_application_schema_version.sql).
    This one refuses to apply unless every migration above it is really present and establishes
    the ledger that later migrations extend.
17. Run [`migrations/015_ordered_pairing_locks.sql`](migrations/015_ordered_pairing_locks.sql).
18. Run [`migrations/016_session_modes_grants_handoffs.sql`](migrations/016_session_modes_grants_handoffs.sql).
19. Run [`migrations/017_mode_conversations.sql`](migrations/017_mode_conversations.sql).
20. Run [`migrations/018_coaching_programs.sql`](migrations/018_coaching_programs.sql).
21. Run [`migrations/019_proactive_delivery_budget.sql`](migrations/019_proactive_delivery_budget.sql).

Apply migrations in numeric order. Migrations 003 and 004 make Pairing backend-only and enforce
the reviewed cross-tenant grants and row-level policies. Migration 005 adds canonical Task states
and the backend-only, idempotent Create Task command boundary. Migration 006 adds canonical
Reminder states and the durable, backend-only scheduling outbox. Migration 007 makes Task
resolution and its Reminder cancellation effects one backend-only transaction. Migration 008
adds the shared atomic Later replacement command. Migration 009 atomically claims Telegram updates
and retains their content-free completion or failure status for safe replay inspection. Migration
010 provides the backend-only, transactionally consistent dashboard snapshot. Migration 011 adds
immutable Reminder occurrence and delivery-attempt evidence, synthetic classification, scheduler
heartbeat/drift state, and content-free reliability metrics. Migration 012 adds the backend-only,
idempotent command that moves one owned pending Task to an explicit Planning Day under ownership
and version checks. Migration 013 adds the durable Activation Journey: the backend-only
acknowledgement, paired profile, private test Reminder, and canonical Activation read model, and
makes Pairing require an acknowledged Journey. Migration 015 orders Pairing's identity-row locks
to prevent crossed Pairing requests from deadlocking. Migration 016 adds Session Mode,
trial-grant, audit, and confirmed-handoff primitives. Migration 017 adds channel-neutral Mode
conversation addresses, Sessions keyed by participant and Mode, and leased handoff execution
claims. The application requires exact schema version 19. These migrations have not been applied
to Supabase by this build; deployment and real-bot verification remain owner actions.

#### Mode conversations and operator access

Daily remains the only live Mode. Coach, Reflect, and Recommender stay Planned until their own
implementation and evaluation gates pass. `GET /api/modes` reports the authenticated participant's
Mode availability, grant expiry, and channel-provided chat links; dashboard chips use this result.

Mode routing is channel-neutral. Threaded channels resolve a `ConversationRef` to a Mode;
unknown conversations enter Daily. Channels without threads use `/mode`, `/mode <id>`, and
`/daily`. These commands also remain available on Telegram for older clients. History is isolated
by Mode-scoped Session, and handoffs need participant confirmation before carrying the selected
request to a target Mode.

For Telegram, enable Threaded Mode and disable user-created threads in BotFather before deploying
this routing. Production startup rejects unsafe topic settings. Every threaded delivery needs an
explicit conversation; Reminders resolve the current primary-channel Daily conversation when they
send. Deleting a private topic does not stop delivery: Telegram can restore it on the next send.
The owner's test bot verified Desktop and iOS behavior; Android and the complete application flow
still need owner verification. Do not enable Threaded Mode on the production bot before this
application slice is reviewed and deployed.

The operator script grants or revokes access with a required reason:

```bash
python scripts/grant_mode.py grant --chat-id 123 --mode coach --operator owner --reason "Internal trial"
python scripts/grant_mode.py revoke --chat-id 123 --mode coach --operator owner --reason "Trial ended"
```

Granting requires a live Mode, defaults to 14 days, and enforces at most five active grants per
Mode in the Store. `--expires-at` can shorten that window. A successful grant creates its channel
conversation; revocation and periodic maintenance close unavailable specialized conversations.
The commands do not make a Planned Mode live and are not participant self-service controls.

#### 3. Run

Telegram needs a public HTTPS URL for the webhook. The simplest option is
[`scripts/dev_tunnel.sh`](scripts/dev_tunnel.sh), which uses Microsoft Dev Tunnels (the same
service as VS Code port forwarding) and starts Amigo behind it in one command:

```bash
brew install devtunnel        # once; first run also asks you to log in with GitHub

scripts/dev_tunnel.sh                # tunnel + API
scripts/dev_tunnel.sh --reload       # tunnel + API with auto-reload
scripts/dev_tunnel.sh --tunnel-only  # tunnel only; run the API from your debugger
```

The script creates a persistent public tunnel named `amigo-<user>` on port 8000, so its URL
(`https://<id>-8000.<region>.devtunnels.ms`) stays the same across runs. It passes that URL to
Amigo as `APP_BASE_URL` without editing `.env`, and prints Telegram's `getWebhookInfo` once the
API is healthy. Override the port or tunnel name with `PORT=` and `TUNNEL_ID=`. Tunnels expire
after 30 days unused; the script recreates one, possibly with a new URL.

To debug in VS Code, set `APP_BASE_URL` in `.env` to the printed tunnel URL once, run
`scripts/dev_tunnel.sh --tunnel-only`, and start the API from the debugger without `--reload`.

Alternatively, with ngrok:

```bash
# Terminal 1 — expose local server to the internet
ngrok http 8000
# Copy the HTTPS URL into .env as APP_BASE_URL

# Terminal 2 — start Amigo
source .venv/bin/activate
uvicorn src.main:app --reload --port 8000
```

On startup, Amigo registers its Telegram webhook at
`{APP_BASE_URL}/webhook`. Use a separate development bot: every startup re-points that bot's
webhook at your machine.

Health check: `curl http://localhost:8000/health`

Readiness check: `curl http://localhost:8000/ready` — returns 503 when the database cannot be
checked, the scheduler heartbeat is stale, or durable scheduler effects have failed.

### Test & Lint

```bash
python -m pytest tests/ -v         # full local suite
ruff check src tests scripts       # lint
python scripts/run_gate_a_eval.py --validate-only
```

Python tests use in-memory fakes and make no Supabase, Telegram, or Gemini calls. CI additionally
is configured to apply every checked-in migration (001–019) to PostgreSQL 15 and run legacy
backfill, two-participant isolation, durable command/outbox, Activation, Mode conversation/handoff,
lock-order, and schema-chain regressions for the exact schema-19 startup gate. This is separate
from staging and Supabase deployment evidence. See
[`tests/fakes.py`](tests/fakes.py) for the shared test doubles.

The controlled before/after runtime procedure is documented in
[`docs/staging-performance-evidence.md`](docs/staging-performance-evidence.md); local concurrency
tests are not a substitute for its dedicated staging workload.

The versioned Gate A model suite, declared-run procedure, evidence contract, and current quota
blocker are documented in [`docs/model-evaluation.md`](docs/model-evaluation.md). A declared run
is only evidence for the revision it executed against:
[`scripts/check_gate_a_evidence.py`](scripts/check_gate_a_evidence.py) recomputes every recorded
fingerprint and rescored category result from retained per-turn trace/response/state evidence,
including Tool call/result IDs, canonical state hashes, chained turns, usage, and cost totals;
verifies the archived last-passing baseline and the SHA-bound candidate/baseline comparison; and
refuses a stale, partial, foreign, baseline-free, human-review-free, or self-declared-passing run.

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
| `ACCESS_MODE` | `open` | Production requires `closed`, `allowlist`, or `invite` |
| `ALLOWED_TELEGRAM_CHAT_IDS` | `""` | Required and non-empty in `allowlist` mode |
| `APP_BASE_URL` | `http://localhost:8000` | Telegram mode |
| `DASHBOARD_URL` | `http://localhost:5173` | Public HTTPS dashboard origin in production |
| `APP_ENV` | `development` | — |
| `LOG_LEVEL` | `INFO` | — |
| `DEFAULT_MODEL` | `gemini-3.5-flash` | — |
| `SMOKE_TEST_CHAT_ID` | — | Smoke checks (`--channel`) |

### Deployment Status

Render is the canonical beta deployment target, described by [`render.yaml`](render.yaml). The
invitation beta must use one always-on service and one scheduler owner; a sleeping free instance
is suitable only for development. The former Fly configuration and workflow are preserved only as
disabled files under `deploy/archive/` and `.github/archive/`; neither can be deployed by default.

The repository does not yet provide a supported self-hosting product. Before a real deployment,
follow the security, staging, monitoring, backup, and end-to-end gates in the
[pre-launch implementation plan](docs/pre-launch-implementation-plan.md).

### Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full picture:
repository structure, design patterns, data flow diagram, key
abstractions, extensibility hooks, and testing strategy.

### What Is Implemented in the Current Worktree

- Dashboard-first Activation application code through verified account, beta-limit
  acknowledgement, secure Telegram Pairing, profile/quiet hours, and a delivered and resolved
  private test Reminder
- Local CLI mode for development (no external services needed)
- Natural-language task extraction with Gemini Flash
- Structured agent planning with tool-based side effects (ADR 0001)
- Reminder scheduling with Done/Skip/Later buttons
- Server-gated dashboard and Telegram access until canonical Activation completion
- Text status updates ("done with slides", "skip gym")
- Authoritative Reminder reconciliation after restart, including drift repair and late recovery
- Immutable Reminder occurrence/attempt timing evidence and separate liveness/readiness checks
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


### Internal Mode candidates and admission controls (22 October 2026)

Migrations 018/019 add owned versioned Coaching Programs, exact-draft approval callbacks,
Program export/deletion, a shared proactive budget ledger and a fenced coaching outbox.
Existing Reminder commitments consume capacity first; historical overflow is recorded as debt,
not silently dropped. New Reminder scheduling can refuse before mutation when the shared profile
budget is full. Coaching uses remaining capacity, selected days, quiet hours, one check-in/day,
one missed follow-up then silence. Weekly review replaces a chosen check-in. Returning to Coach resumes that gate; program approval and extension remain separate choices.

Coach, Reflect and fictional laundry Recommender have authored instructions, isolated Toolsets
and versioned fictional evaluation suites. They remain Planned pending the sole final Gemini
batch after shared source changes stop. Candidate runner output cannot certify release/fallback.
No provider fallback is declared without complete current evidence and human review.

Coach and Reflect additionally deny real admission by default. Missing reviewed notices,
consent/retention/account-wide rights and qualified wellbeing evidence cannot be replaced with
an operator grant or a passing model test. Program export/deletion covers Program records and
entries only; retained conversation Messages/provider copies remain. Account-wide deletion and
backup erasure are not claimed. Reflect stores no Mood Entries, Memory, exercises or profile
inferences; its empty resource registry supplies only static general emergency guidance, never
stale contact details. CBT personal input remains off. No deployment or Supabase change occurred.
