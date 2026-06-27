# Amigo — Project Wrap-Up & Production Launch Guide

This guide covers everything needed to take Amigo from its current
dogfooding state to a production launch. It is organized into two
launch phases:

- **Phase A — Telegram Bot** (standalone, no dashboard dependency)
- **Phase B — Web Dashboard** (requires identity linking architecture)

This separation exists because the bot and the dashboard use **two
different identity systems** today (see Section 3.1). Shipping the bot
first lets you go live immediately while the dashboard integration is
built.

---

## Current State

| Metric | Value |
|--------|-------|
| Tests | 60 passing, 0 failing |
| Lint | Clean (`ruff check src tests scripts`) |
| Deprecation warnings | 89 (from 8 call sites using `datetime.utcnow()`) |
| Agent architecture | Pydantic AI tool-calling loop (ADR 0002) ✅ |
| Deployment infra | Dockerfile + fly.toml + GitHub Actions CI/CD ✅ |
| Core loop | Task extraction → reminders → snooze → morning planning ✅ |

---

## 1. Code Cleanup & Bug Fixes (Do First)

These are self-contained tasks with no architectural decisions. Do them
before any deployment.

### 1.1 Fix `datetime.utcnow()` deprecation (8 call sites)

Replace `datetime.utcnow()` with `datetime.now(datetime.UTC)` in:

| File | Lines |
|------|-------|
| [fakes.py](tests/fakes.py) | L72, L95, L96, L107, L113, L123, L171, L196 |
| [test_session_rollover.py](tests/test_session_rollover.py) | L36, L51, L101 |

> [!NOTE]
> `tests/fakes.py` is shared test infrastructure — per AGENTS.md, never
> auto-delete it, but these are safe in-place edits.

### 1.2 Delete dead code

| Target | Reason |
|--------|--------|
| `src/providers/` directory | Contains only a docstring saying "deprecated." No imports reference it. |
| `src/agent/prompts.py` L53–55 | Three empty-string constants (`TASK_EXTRACTION_PROMPT`, `REMINDER_TIME_PROMPT`, `TASK_STATUS_PROMPT`) marked deprecated. |
| `ContextBuilder.build()` method | The public `build()` and `_build_profile_block()` in [context.py](src/memory/context.py) are never called after the Pydantic AI migration. Only `_build_tasks_block`, `_get_yesterday_summary`, and `_get_truncated_messages` are still used. |

### 1.3 Category-aware AM/PM disambiguation

Currently [parse_time_expression](src/agent/agent.py) calls `dateparser`
with no category hint. "Remind me about dinner at 8" resolves to 8:00 AM.

**Fix:** Add category-aware rules to `parse_time_expression`:

```python
PM_CATEGORIES = {"dinner", "evening", "social", "night"}
AM_CATEGORIES = {"breakfast", "morning", "gym"}

def parse_time_expression(time_expr: str, timezone: str,
                          category: str = "other") -> str | None:
    settings = {
        "TIMEZONE": timezone,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": now_in_tz(timezone).replace(tzinfo=None),
    }
    # Inject AM/PM preference based on task category
    if category.lower() in PM_CATEGORIES:
        settings["PREFER_TIME_DIRECTION"] = "pm"
    elif category.lower() in AM_CATEGORIES:
        settings["PREFER_TIME_DIRECTION"] = "am"

    parsed = dateparser.parse(time_expr, settings=settings)
    if parsed is None:
        return None
    return parsed.strftime("%H:%M")
```

Update the `create_task` tool in [agent.py](src/agent/agent.py) to pass
`category` through to `_schedule_reminder_for_task`.

### 1.4 Webhook idempotency

The [webhook endpoint](src/main.py) currently has no error handling. If
the agent crashes mid-turn, Telegram retries the same update for up to
~26 hours, potentially causing duplicate processing.

**Fix:** Always return `{"ok": True}` and wrap the handler:

```python
@app.post("/webhook")
async def telegram_webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    data = await request.json()
    update = Update.de_json(data, channel.bot)

    try:
        if update.message and update.message.text:
            await handlers.handle_message(
                chat_id=update.message.chat_id, text=update.message.text,
            )
        elif update.callback_query:
            query = update.callback_query
            await query.answer()
            await handlers.handle_callback(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                data=query.data,
            )
    except Exception:
        logger.exception("Error processing update %s", update.update_id)

    return {"ok": True}  # Always acknowledge to prevent retries
```

---

## 2. Production Hardening (Phase A — Bot Only)

These tasks make the Telegram bot production-ready without touching the
dashboard.

### 2.1 Token & cost tracking

The `MemoryStore.log_usage()` method [already exists](src/memory/store.py)
but is never called. Wire it into [handle_message](src/agent/agent.py):

```python
result = await amigo_agent.run(
    user_message, model=_get_model_name(), deps=deps,
    message_history=message_history if message_history else None,
)
response = result.output

# Track token usage
usage = result.usage()
await deps.store.log_usage(
    user_id=user_id,
    model=_get_model_name(),
    input_tokens=usage.request_tokens or 0,
    output_tokens=usage.response_tokens or 0,
    session_id=deps.session_id,
)
```

> [!IMPORTANT]
> **Store sync rule**: `InMemoryStore` and `FakeStore` must also have a
> matching `log_usage()` method. `InMemoryStore` already has one. Verify
> `FakeStore` does too.

### 2.2 Tool-level idempotency

Modify [CreateTaskTool](src/tools/tasks.py) to check for duplicate titles
on the same day before creating:

```python
async def run(self, *, user_id, title, category="other",
              session_id=None, suggested_time=None, timezone="UTC"):
    # Dedup: skip if same title exists today
    today_tasks = await self.store.get_today_tasks(user_id, timezone)
    for t in today_tasks:
        if t["title"].lower().strip() == title.lower().strip():
            return {"task": t}  # Return existing task

    task = await self.store.create_task(...)
    return {"task": task}
```

### 2.3 Prompt restructure (cost optimization)

Split the system prompt into a **static prefix** (persona, voice, rules)
and a **dynamic suffix** (current_time, task list, pending IDs). This
enables prompt caching — the static prefix is identical across calls and
can be cached by the model provider.

Currently [_build_system_prompt](src/agent/agent.py) concatenates
everything into one string on every turn. Refactor to:

1. Register a static system prompt via `@amigo_agent.system_prompt`
   that returns only the persona/rules from `build_system_prompt()`.
2. Inject the dynamic context (time, tasks, yesterday summary) as a
   separate system prompt part or into the user message.

### 2.4 Observability

| Tool | Purpose | Priority |
|------|---------|----------|
| **Logfire** | Pydantic AI trace visualization, token counts, tool call latency | High |
| **Sentry** | Runtime exception capture for FastAPI | Medium |
| **Structured logging** | JSON logs with `user_id`, `session_id`, `turn_duration_ms` | Medium |

### 2.5 Scheduler — no changes needed yet

The guide previously recommended migrating to Redis-backed ARQ or
`SQLAlchemyJobStore`. **This is premature.**

The current setup is already production-safe for a single-machine
deployment because:

- [fly.toml](fly.toml) pins `min_machines_running = 1` and
  `auto_stop_machines = "off"` — exactly one machine always runs.
- [claim_reminder_for_send](src/memory/store.py) implements **atomic
  claiming** via `UPDATE ... WHERE status = 'pending'` — even if
  two scheduler instances existed, only one would send.
- Pending reminders are reloaded from the database on startup via
  [reload_pending](src/scheduler/reminders.py).

**Revisit when:** you scale beyond one machine, or add cron-triggered
proactive check-ins that need distributed coordination.

### 2.6 Anti-nag governor (Phase 1b — after launch)

Place anti-nag checks **before** the LLM call in
[TurnProcessor.handle](src/bot/turns.py), not inside agent tools.
This avoids paying latency and token cost just to decide not to reply.

Constraints to enforce:
- Per-category cooldown: 45 minutes minimum between proactive messages
- Daily budget: max N proactive messages/day (configurable, default 4)
- Progressive back-off: 3 consecutive ignored → pause category 24hrs
- Explicit mute per category

### 2.7 Crisis gating (required before Reflect mode ships)

> [!CAUTION]
> **Non-negotiable.** Do not ship any wellbeing/reflect mode without this.

Implement deterministic keyword/regex matching in `BotHandlers` before
the message reaches the agent. If distress signals are detected:

1. Bypass the LLM entirely
2. Send a supportive message with helpline information
3. Log the event for review

---

## 3. Dashboard Integration (Phase B)

> [!IMPORTANT]
> The dashboard requires solving the **identity linking problem** first.
> Do not attempt to deploy the dashboard before completing Section 3.1.

### 3.1 The identity mismatch problem

The system currently has **two unlinked identity systems**:

| System | Identity | Created when |
|--------|----------|-------------|
| Telegram bot | `user_profiles.user_id` (UUID via `gen_random_uuid()`) | User sends first message to bot |
| Supabase Auth | `auth.uid()` (UUID from Supabase Auth) | User signs up on the dashboard |

The dashboard's Supabase client uses the anonymous key and respects RLS.
For RLS policies to work, the database needs to know which `user_profiles`
row belongs to which `auth.uid()`.

**Solution:** Add a `supabase_auth_id` column to `user_profiles` and
populate it during a pairing flow.

### 3.2 Migration: `002_auth_linking_and_rls.sql`

> [!WARNING]
> Do **not** edit `001_initial_schema.sql` — it has already been applied
> to the production database.

Create `migrations/002_auth_linking_and_rls.sql`:

```sql
-- Link Supabase Auth identity to application user
ALTER TABLE user_profiles
  ADD COLUMN supabase_auth_id UUID UNIQUE;

-- Pairing tokens for Telegram account linking
CREATE TABLE pairing_tokens (
    token TEXT PRIMARY KEY,
    supabase_auth_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_pairing_tokens_expiry
  ON pairing_tokens(expires_at) WHERE consumed = FALSE;

-- RLS policies (using the linked auth identity)
CREATE POLICY "Users see own profile"
  ON user_profiles FOR SELECT TO authenticated
  USING (supabase_auth_id = auth.uid());

CREATE POLICY "Users update own profile"
  ON user_profiles FOR UPDATE TO authenticated
  USING (supabase_auth_id = auth.uid())
  WITH CHECK (supabase_auth_id = auth.uid());

CREATE POLICY "Users see own tasks"
  ON tasks FOR ALL TO authenticated
  USING (user_id IN (
    SELECT user_id FROM user_profiles
    WHERE supabase_auth_id = auth.uid()
  ));

CREATE POLICY "Users see own reminders"
  ON reminders FOR ALL TO authenticated
  USING (user_id IN (
    SELECT user_id FROM user_profiles
    WHERE supabase_auth_id = auth.uid()
  ));

CREATE POLICY "Users see own sessions"
  ON sessions FOR SELECT TO authenticated
  USING (user_id IN (
    SELECT user_id FROM user_profiles
    WHERE supabase_auth_id = auth.uid()
  ));

CREATE POLICY "Users see own messages"
  ON messages FOR SELECT TO authenticated
  USING (user_id IN (
    SELECT user_id FROM user_profiles
    WHERE supabase_auth_id = auth.uid()
  ));
```

### 3.3 Telegram pairing flow

**Security requirements for pairing tokens:**
- Cryptographically random (≥ 32 hex chars)
- Short-lived (15 minute TTL)
- Single-use (mark `consumed = TRUE` after successful pairing)
- Tied to the initiating `auth.uid()`

**Flow:**

1. Dashboard user clicks "Connect Telegram" → frontend calls a Supabase
   Edge Function that generates a token, inserts into `pairing_tokens`,
   returns it.
2. UI renders QR code / deep link: `https://t.me/amigo_agent_bot?start=pair_<TOKEN>`
3. User opens the bot → Telegram sends `/start pair_<TOKEN>` as a message.
4. **New handler branch needed** in [BotHandlers.handle_message](src/bot/handlers.py):
   parse `/start pair_<TOKEN>`, validate the token, link `supabase_auth_id`
   to the user's `user_profiles` row, mark token consumed.

> [!NOTE]
> The current `handle_message` has no `/start` payload parsing. A new
> branch must be added before the allowlist check.

### 3.4 Connect dashboard to real data

Replace mock data arrays in [DashboardView.jsx](web/src/components/DashboardView.jsx)
with Supabase queries:

```javascript
import { supabase } from '../supabase'

// Fetch today's tasks
const { data: tasks } = await supabase
  .from('tasks')
  .select('*')
  .eq('created_date', new Date().toISOString().split('T')[0])
  .order('created_at')

// Subscribe to real-time updates
supabase
  .channel('tasks')
  .on('postgres_changes', { event: '*', schema: 'public', table: 'tasks' },
    (payload) => { /* update local state */ })
  .subscribe()
```

Real-time subscriptions ensure that when a user marks a task "Done" in
Telegram, the dashboard updates immediately without a page refresh.

### 3.5 Visual polish

Apply the fixes documented in [next-todo.md](web/next-todo.md):
- Glassmorphism on Horizon card (backdrop-filter + semi-transparent bg)
- Serif typography for greeting heading
- Sidebar active state (left-border accent, not solid fill)
- Fix Recommender chip disabled state
- Background color `#14121A`, text color `#F7F3EC`

---

## 4. Deployment Playbook

### 4.1 Supabase production setup

1. Create a new project in the Supabase Dashboard.
2. Run [001_initial_schema.sql](migrations/001_initial_schema.sql) in the
   SQL Editor.
3. (Phase B only) Run `002_auth_linking_and_rls.sql`.
4. Enable Email/Password auth under **Authentication → Providers**.
5. Under **Authentication → URL Configuration**, add your dashboard's
   production URL to the **Site URL** and **Redirect URLs** fields.

### 4.2 Telegram bot registration

1. Chat with [@BotFather](https://t.me/BotFather) on Telegram.
2. `/newbot` → name it (e.g., "Amigo Friend") → get the bot token.
3. Set command shortcuts: `/feedback` and `/start`.
4. Store the token securely — it goes into Fly.io secrets.

### 4.3 Deploy backend to Fly.io

The project already has a working [Dockerfile](Dockerfile),
[fly.toml](fly.toml), and [deploy workflow](.github/workflows/deploy.yml).

```bash
# One-time setup
fly launch --no-deploy

# Set production secrets
fly secrets set \
  GOOGLE_API_KEY="your-gemini-key" \
  TELEGRAM_BOT_TOKEN="your-bot-token" \
  SUPABASE_URL="https://your-project.supabase.co" \
  SUPABASE_SERVICE_KEY="your-service-role-key" \
  TELEGRAM_WEBHOOK_SECRET="$(openssl rand -hex 32)" \
  ALLOWED_TELEGRAM_CHAT_IDS="your-chat-id" \
  APP_ENV="production"

# Deploy
fly deploy --remote-only
```

On startup, the FastAPI app automatically registers the Telegram webhook
at `{APP_BASE_URL}/webhook` (configured in fly.toml as
`https://amigo.fly.dev`).

**Alternatively**, use the GitHub Actions deploy workflow:

1. Create a GitHub environment named `production`.
2. Add `FLY_API_TOKEN` as an environment secret (`fly tokens create deploy -x 999999h`).
3. Enable manual approval on the `production` environment.
4. Trigger the workflow via `workflow_dispatch`.

### 4.4 Deploy dashboard to Vercel (Phase B only)

1. Create a Vercel project pointing to the git repo.
2. Set root directory to `web`.
3. Build command: `npm run build`, output: `dist`.
4. Environment variables:
   - `VITE_SUPABASE_URL` — your Supabase project URL
   - `VITE_SUPABASE_ANON_KEY` — your Supabase anonymous API key
5. Under Supabase **Authentication → URL Configuration**, add the
   Vercel production URL to **Site URL** and **Redirect URLs**.

### 4.5 Verify

```bash
# Health check
curl https://amigo.fly.dev/health

# Logs
fly logs

# Send a test message to the bot on Telegram
# Verify onboarding flow completes
```

---

## 5. CI/CD Gaps to Close

The project has existing GitHub Actions but they have gaps:

| Gap | File | Fix |
|-----|------|-----|
| Frontend not built in CI | [ci.yml](.github/workflows/ci.yml) | Add a job: `cd web && npm ci && npm run build` |
| `DEFAULT_MODEL` not in fly.toml | [fly.toml](fly.toml) | Add `DEFAULT_MODEL = "gemini-2.5-flash"` to `[env]` (currently defaults to `gemini-3.5-flash` in config.py — verify this is intentional) |
| Smoke check not in CI | [ci.yml](.github/workflows/ci.yml) | Add `python scripts/smoke_check.py --scheduler` step after tests |

---

## 6. Release Checklist

### Phase A — Telegram Bot (ship first)

| # | Task | Critical? | Status |
|---|------|-----------|--------|
| 1 | Fix `utcnow()` in 8 call sites | No | ☐ |
| 2 | Delete `src/providers/`, deprecated prompt constants, dead `ContextBuilder` methods | No | ☐ |
| 3 | Add category-aware AM/PM to `parse_time_expression` | Yes | ☐ |
| 4 | Add webhook error handling (always return ok) | Yes | ☐ |
| 5 | Wire token tracking into `handle_message` | No | ☐ |
| 6 | Add tool-level idempotency to `CreateTaskTool` | No | ☐ |
| 7 | Run `001_initial_schema.sql` on production Supabase | Yes | ☐ |
| 8 | Create production Telegram bot via BotFather | Yes | ☐ |
| 9 | Deploy to Fly.io with all secrets configured | Yes | ☐ |
| 10 | Verify: health check, send test message, onboarding flow | Yes | ☐ |
| 11 | Run `scripts/smoke_check.py --all` against production | Yes | ☐ |

### Phase B — Web Dashboard (ship after bot is stable)

| # | Task | Critical? | Status |
|---|------|-----------|--------|
| 12 | Create and apply `002_auth_linking_and_rls.sql` | Yes | ☐ |
| 13 | Build pairing token generation (Edge Function or API) | Yes | ☐ |
| 14 | Add `/start pair_<TOKEN>` handler to BotHandlers | Yes | ☐ |
| 15 | Replace mock data with Supabase queries + Realtime | Yes | ☐ |
| 16 | Apply visual polish from next-todo.md | No | ☐ |
| 17 | Add frontend build to CI pipeline | Yes | ☐ |
| 18 | Deploy dashboard to Vercel | Yes | ☐ |
| 19 | Configure Supabase Auth redirect URLs | Yes | ☐ |

### Phase 1b — After launch (not blocking release)

| # | Task |
|---|------|
| 20 | Prompt restructure for caching (static prefix + dynamic suffix) |
| 21 | Anti-nag governor in TurnProcessor |
| 22 | Proactive evening check-ins |
| 23 | Crisis gating (required before Reflect mode) |
| 24 | Logfire + Sentry observability |
