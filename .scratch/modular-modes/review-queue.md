# Modes build review queue

## Phase 0 — 2026-10-22

- Commit: `ac6b235` (housekeeping; queue recorded in following slice).
- Files: AGENTS.md, CLAUDE.md, HANDOFF.md (deleted), docs/adr/0003-mode-topics.md,
  .scratch/modular-modes/issues/03-switch-modes-with-confirmed-handoffs.md,
  .scratch/mode-expansion-planning/cbt-research-mvp/README.md,
  .scratch/mode-expansion-planning/decisions/05-cbt-research-protocol.md.
- Protected edits: AGENTS.md updated as explicitly authorized; no protected runtime/SQL edits.
- Baseline: clean develop/e73a6bd; 638 passed in 16.09s, matching spec.
- Verification: 638 passed in 14.39s; Gate A currency 111 passed in 9.87s;
  Ruff `All checks passed!`; scheduler smoke `in-memory APScheduler reminder fired through channel`;
  git diff --check passed. No live Gate A run; no model requests.
- Instruction inventory: only AGENTS.md and CLAUDE.md found; CLAUDE.md now imports AGENTS.md.
  Skills preserved. Daily instructions/schema untouched.
- Decisions: build rules and lifted gates recorded; 8-request cap superseded by model ladder;
  CBT personal input disabled. Unfinished selector and pending Store/crash review moved to trackers.
- Open: Phase 3 owner test-bot spike; Phase 2 Store review; all later implementation.

## Phase 1 — 2026-10-22

- Commits: `c22911c` runtime ladder/Gate A/accounting; `cc79c24` fictional CBT selector.
- Files: pyproject.toml; src/agent/claude_cli_model.py; src/agent/runtime.py; src/config.py;
  src/runtime_config.py; src/model_usage.py; src/evaluation/gate_a.py;
  scripts/check_gate_a_evidence.py; scripts/run_gate_a_eval.py;
  tests/test_dev_models.py; tests/test_gate_a_dev_models.py; tests/test_model_usage.py;
  CBT MVP README.md, model_selector.py (renamed), research_cli.py, research_engine.py,
  test_model_selector.py; this queue.
- Protected edits: src/config.py (DEV_MODEL, OLLAMA_BASE_URL only).
- Verification: full backend 678 passed in 12.14s; CBT 57 passed in 1.50s;
  Gate A currency 111 passed in 5.42s; Ruff src/tests/scripts + CBT clean; whitespace clean;
  scheduler smoke passed. Daily golden/schema tests unchanged and passing.
- Actual fictional Daily Turn through handler/runtime: Claude sonnet resolved to claude-sonnet-5-5,
  one Task/no Reminder; Ollama qwen3.5:4b, one Task/no Reminder. Claude API key unset; tools/MCP
  disabled and session persistence disabled. Sandbox OAuth/local-network restrictions required
  approved external execution. No .env reads in smoke fixtures; no production Stores used.
- Gemini totals: 0 live requests, 0 tokens; metadata file not created by mocks (tmp_path only).
  No live Gate A certification claimed; non-Gemini development evidence cannot certify it.
- Decisions: explicit DEV_MODEL required to preserve empty-setting DEFAULT_MODEL behavior;
  Claude malformed output fails once, generic error; JSON Schema args checked before Tools;
  jsonschema declared directly (already installed). CBT per-run four stays; obsolete batch cap gone.
- Open: Phase 1b per-model eval allowlist; real owner pin requires key/identity and passing evals.

### Phase 1 CLI follow-up

- Baseline CLI seed lacked Dashboard Activation; real CLI smoke initially refused the seeded user.
  CLI now seeds a simulated completed Activation in its disposable InMemoryStore through existing
  commands and completes both simulated outbox effects. No production gate or Store API changed.
- Files: src/cli.py, tests/test_cli_seed.py. No protected edits. Focused regression 1 passed;
  global Ruff passed. Combined working tree full suite: 737 passed in 9.89s.
- Actual `DEV_MODEL=ollama:qwen3.5:4b APP_CHANNEL=cli APP_ENV=development ACCESS_MODE=open
  GOOGLE_API_KEY= python -m src.cli` completed Daily with `tools=[create_task]`, outcome ok,
  answering model qwen3.5:4b; no pending Reminder and no scheduler error on final run.
- Earlier fixture attempt exposed an existing naive/aware timestamp comparison in local
  claim_scheduler_effects for Activation outbox rows. Simulated fixture effects are now completed
  before the scheduler starts; broader local Activation/outbox timestamp parity remains open.
- CLI follow-up commit: `19ac8e0`.

## Phase 1b — 2026-10-22

- Commit: `2bc1492`.
- Files: .env.example; src/agent/runtime.py; src/config.py; src/runtime_config.py;
  src/model_routing.py; src/evaluation/model_policy.py; src/evaluation/gate_a.py;
  tests/test_model_routing.py; .scratch/amigo-complete-product/decisions/31-participant-model-choice.md.
- Protected edits: src/config.py (owner maps/platform key; hidden input values in errors).
- Evidence: full combined suite 740 passed in 9.11s; Gate A currency 111 passed in 5.44s;
  global Ruff and whitespace clean; scheduler smoke passed. No live Gate A run.
- Precedence: DEV_MODEL > owner/internal pin > per-Mode override > configured default.
  Existing ModeDefinition primary policy preserved below explicit operator routing for compatibility.
  Unknown prefixes fail startup; production rejects subscription CLI anywhere in configured routes.
- Separate per-Mode/model allowlist validates retained artifact hash, current source/dependency/
  instruction/tool/settings currency, full run scores and artifact-bound human review. It explicitly
  excludes Gemini-only certification from generic model approval; Gate A checker still rejects
  non-Gemini evidence. No allowlist entry fabricated or model enabled without evidence.
- Pin warnings content-free; requested_model records resolved ID. Mock provider test verifies
  Anthropic platform key; mocked Turn verifies anthropic:claude-haiku-5-5 requested-model record.
- Actual owner API pin not configured/run: owner's key/identity not supplied, .env unchanged.
  Real participants never pinned. Participant model choice deferred (decision 31).
- Gemini totals remain 0 requests/0 tokens. No new privacy promise or production data change.
- Root review corrected naive-UTC review-time conversion; timezone regression passes.
- Open: owner API-pin smoke optional; actual per-Mode final evals belong to Phase 5.

## Phase 2 — 2026-10-22

- Commit: `0eb53d4`.
- Files: tests/test_handoff_crash_window.py;
  .scratch/modular-modes/proposals/issue03-store-review.md; this queue (Phase 1b entry).
- Protected edits: none. Store/SQL bytes unchanged; no findings required fixes.
- Independent Standards PASS; independent Spec PASS. Each reviewer ran 67 Store contract cases
  (67 passed in 0.06s). Supabase coverage remains a query/RPC double, not SQL execution.
- Crash injection at confirmation-before-execution reproduces request loss for both local Stores:
  2 passed in 0.02s. Detailed scope and evidence in issue03-store-review.md.
- Full combined tree: 740 passed in 9.50s; currency 111 passed in 5.44s; Ruff/whitespace clean;
  scheduler smoke passed. No live Gate A certification; Gemini 0 requests/0 tokens.
- Open: Phase 4 durable execution + Tool commit replay safety. Claims alone must not be described
  as proof of exactly-once side effects.

## Phase 3 — 2026-10-22 — STOP, owner test required

- Commit: `7efa884`.
- Files: scripts/spike_private_topics.py; tests/test_topic_spike.py;
  .scratch/modular-modes/proposals/topic-spike-runbook.md.
- Protected edits: none. No bot token or Settings loaded; no actual bot calls.
- 25 mocked spike tests passed; combined spike/Store/crash 94 passed in 0.12s.
  Full backend 740 passed in 9.50s; Gate A currency 111 passed in 5.44s;
  global Ruff/whitespace passed; scheduler smoke passed. Script --help passed.
- Probe checks test-only acknowledgement/environment production-token refusal; topic capability;
  no configured webhook; private chat; topic creation/send; desktop/iOS/Android thread IDs;
  unthreaded send; deleted-topic rejection. Errors/console omit token, URL and incoming content.
- Owner must enable private topic mode on a disposable test bot, run the linked runbook, report
  three client/version observations, unthreaded location and deleted-topic behavior. Do not paste
  tokens. ADR remains Accepted, pending spike. Phase 4 not started; no migrations written/applied.
- Gemini total 0 requests/0 tokens. No push, deploy, Supabase migration, .env edit, real-participant
  Claude pin, or CBT personal input. Phase 5/6 implementation remains outstanding.

## Phase 3 review fixes — 2026-10-22

Owner review findings at the end of give-me-a-plan-wild-unicorn.md addressed before any
owner topic spike or Phase 4 implementation. One commit per finding; no protected-file edits.

1. **Gemini accounting — `a526d5c`**
   - Files: src/agent/runtime.py, src/model_usage.py, tests/test_model_usage.py.
   - Production factory builds exact plain GoogleModel for google/google-gla, including after a
     development instance was cached. Runtime cache is separated by production status.
   - Development and explicit eval runner retain LoggedGoogleModel; it uses public request /
     ModelResponse.usage, with no overrides of Pydantic AI private methods. Provider failures,
     malformed provider responses and cancellation retain metadata-only error/unknown-token counts.
     Local validation errors are not logged as provider requests.
   - All mkdir/open/write/close work runs through asyncio.to_thread. Thread regression proves
     writes occur outside the event-loop thread. Production request test proves logger not called.
   - Red regressions: 7 failed / 4 passed before fix (production type/cache, synchronous I/O,
     public-result accounting). Independent review found malformed-response accounting gap;
     actual public request + mocked SDK malformed-response regression now passes.

2. **Claude environment — `cdcc962`**
   - Files: src/agent/claude_cli_model.py, tests/test_dev_models.py;
     CBT MVP model_selector.py, test_model_selector.py.
   - Both subprocesses share an allowlist: PATH, HOME, USER, LANG, TERM, CLAUDE_CODE_OAUTH_TOKEN.
     Only explicit subscription OAuth auth is retained; no application keys or provider overrides.
     CBT's output-token setting is a fixed trusted value, not inherited environment input.
   - Tests assert SUPABASE_SERVICE_KEY, TELEGRAM_BOT_TOKEN, GOOGLE_API_KEY, ANTHROPIC_API_KEY,
     arbitrary secrets and provider endpoint/auth overrides never reach subprocesses.
     Focused runtime/harness selection tests: 48 passed in 1.23s; touched-file Ruff clean.

3. **Spike token — `e226738`**
   - Files: scripts/spike_private_topics.py, tests/test_topic_spike.py,
     .scratch/modular-modes/proposals/topic-spike-runbook.md.
   - Token read only from TEST_BOT_TOKEN process environment. --token removed; obsolete invocation
     fails without echoing arguments. Missing/blank test token and matching production token refused.
     --test-bot remains mandatory. Runbook avoids token values in command arguments/history.
   - Focused spike tests: 31 passed. Help output confirms no --token option. No bot calls executed.

4. **Local scheduler timestamps — this commit, `Normalize scheduler outbox claim timestamps to UTC`**
   - Files: src/memory/memory_store.py, src/memory/store.py, tests/fakes.py,
     tests/test_scheduler_effect_timestamps.py;
     .scratch/scheduler-effect-timestamps/issues/01-normalize-local-outbox-claim-timestamps.md;
     this review queue.
   - Local issue opened, reproduced, fixed and closed with evidence. Actual Activation outbox claim
     reproduced compare/subtract TypeErrors; mixed offsets also reproduced wrong oldest-first order.
     Red regression: 10 failed, 3 passed in 0.12s. Green regression: 13 passed; focused
     Activation/scheduler group 51 passed in 1.01s.
   - Both local Stores normalize current/available/claimed/created timestamps to UTC instants;
     legacy naive values mean UTC. Tests cover real Activation rows, naive/aware clocks, offsets,
     future eligibility, lease expiry/boundary, chronological limits, attempts and detached results.
   - MemoryStore keeps exact claim_scheduler_outbox RPC; docstring clarified. Adapter contract test
     verifies delegation/returned offset rows/null handling. This is mocked adapter coverage, not
     a new PostgreSQL execution. No migration or new reachable module required.

**Final integrated verification (all four fixes):**

- `.venv/bin/python -m pytest tests/ -q`: **766 passed in 8.88s**.
- Gate A currency: **111 passed in 5.61s**; currency test source unchanged.
- Separate fictional CBT harness: **57 passed in 0.87s**.
- Ruff src/tests/scripts + CBT harness: **All checks passed!**
- Scheduler smoke: **in-memory APScheduler reminder fired through channel**.
- git diff --check clean. Daily instructions/Tool schema unchanged; golden tests passed.
- No live Gate A certification or model requests. Gemini total remains 0 requests/0 tokens.
  No production usage file write, .env edit, push, deploy, Supabase migration, participant Claude
  pin or CBT personal input. All runtime evidence tests use mocks/temporary metadata paths.

**STOP:** spike script ready for owner run with TEST_BOT_TOKEN, --test-bot and private --chat-id.
ADR 0003 remains Accepted, pending spike. Phase 4 not started; owner client observations required.


## Phase 3 spike acceptance — 22 October 2026

- Commit: `2ae3fcf` Accept channel-neutral Mode conversations after owner topic spike.
- Files: docs/adr/0003-mode-topics.md; .scratch/modular-modes/proposals/topic-spike-runbook.md.
- ADR Accepted. Owner Desktop/iOS PASS; Android not tested. User-created topics disabled;
  bot-created topics still work. Unthreaded sends created topics; sends restore deleted topics.
- Production requires topics on, user-created topics off. No unthreaded resend or dependency on
  “thread not found”. Unknown conversations become Daily aliases, canonical Mode state is neutral.
- No builder live Telegram call, production change, secret edit, or privacy promise change.

## Phase 4 — channel-neutral routing, conversations and durable handoffs — 22 October 2026

- Commit: this slice, `Route Modes through channel-neutral conversations and durable handoffs`.
- Files touched:
  - .github/workflows/ci.yml
  - README.md
  - docs/architecture.md
  - docs/capability-matrix.md
  - docs/pre-launch-gap-analysis.md
  - scripts/check_schema_chain.py
  - scripts/run_gate_a_eval.py
  - scripts/smoke_check.py
  - src/agent/context.py
  - src/agent/modes.py
  - src/agent/policies.py
  - src/agent/runtime.py
  - src/bot/handlers.py
  - src/bot/turns.py
  - src/channels/base.py
  - src/channels/cli.py
  - src/channels/telegram.py
  - src/cli.py
  - src/evaluation/gate_a.py
  - src/main.py
  - src/memory/context.py
  - src/memory/memory_store.py
  - src/memory/modes.py
  - src/memory/sessions.py
  - src/memory/store.py
  - src/scheduler/reminders.py
  - src/schema.py
  - src/telemetry.py
  - src/tools/context.py
  - src/tools/toolsets.py
  - src/turns.py
  - tests/fakes.py
  - tests/sql/app_schema_version.sql
  - tests/test_reminders.py
  - tests/test_scheduler.py
  - tests/test_turn_processing.py
  - web/src/components/ModeChips.jsx
  - .scratch/modular-modes/proposals/017-independent-verification.md
  - .scratch/modular-modes/proposals/issue04-coaching-store-design.md
  - migrations/017_mode_conversations.sql
  - scripts/check_mode_handoff_execution.py
  - scripts/grant_mode.py
  - src/agent/recommender.py
  - src/api/modes.py
  - src/bot/modes.py
  - src/conversations.py
  - src/handoffs.py
  - src/tools/handoff_execution.py
  - src/tools/handoffs.py
  - src/tools/recommender.py
  - tests/sql/assert_017_mode_conversations.sql
  - tests/test_channel_conversations.py
  - tests/test_grant_mode_script.py
  - tests/test_mode_conversation_store.py
  - tests/test_mode_delivery.py
  - tests/test_mode_routing.py
  - tests/test_modes_api.py
- Protected edits: migrations/017_mode_conversations.sql; scripts/smoke_check.py. No .env,
  Supabase, deployment, push or production model pin changes.
- Migration independently reviewed by dev_runtime. Corrections and exact-byte SQL evidence:
  .scratch/modular-modes/proposals/017-independent-verification.md. Full 37-file CI SQL chain
  on fresh local PostgreSQL15 passed; schema-chain predecessor/gap checks passed at version17;
  Activation lock-order probe passed 30 trials/155 calls. Separate fresh DB proved pre017
  backfill, eight concurrent claims→one winner, expired-token fencing, fixed clock/bound Session,
  append-only replay and terminal completion. No production DB used.
- Canonical conversations + neutral alias endpoints. Every topics-enabled Telegram send resolves
  an explicit conversation, including unpaired/pairing/access errors. Unknown incoming endpoints
  select Daily without replacing canonical proactive delivery. Startup refuses unsafe production
  topic settings. CLI and threaded fake share routing/history/grant/handoff contracts.
- Mode Sessions isolate histories and yesterday summaries; withdrawal refuses instead of silently
  running Daily. Reminder/recovery delivery re-resolves current primary endpoint and Daily.
- Confirmation is single-use; persisted public model response steps precede side effects, preserve
  opaque provider signatures and reject private reasoning. Stable clock, timing preferences,
  target Session, command receipts and cancellation ID snapshots survive crashes. Recovery shares
  the live webhook participant lock; CLI recovery shares its input lock. Lease is not a claim of
  exactly-once external message delivery.
- Daily instructions and Tool schema golden tests unchanged. Fingerprint closure strengthened to
  include handlers and newly reachable modules; currency tests were not weakened.
- Gate A certification: NOT CURRENT. check_gate_a_evidence.py refused because
  evidence/gate-a/latest.json does not exist. No Gemini request made; final model evaluation
  belongs to Phase5, no invented passing artifact or fallback evidence.
- Validation: full suite **892 passed in 9.52s**; Ruff **All checks passed**; scheduler
  smoke **in-memory APScheduler reminder fired through channel**; diff whitespace clean.
  Focused routing/Store/currency suite previously **172 passed in 5.69s**, then recovery
  regressions added; complete suite includes currency and unchanged Daily golden checks.
- Frontend: ESLint passed; Vite production build passed (1986 modules). Dashboard reads /api/modes.
- Provisional choices: neutral alias table alongside canonical conversations; retained response
  steps for durable replay; no threadless fallback. Android and owner end-to-end flow remain
  unverified. Live --channel smoke now requires linked account/schema to resolve explicit Daily;
  scheduler smoke remains in memory. Owner applies reviewed migration/deploys separately.
