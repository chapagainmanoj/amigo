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


## Phase 5 — gated Mode candidates and durable coaching — 22 October 2026

- Commit: this slice, `Build gated Mode candidates and durable coaching workflows`.
- Phase4 routing commit resolved: `cab0751` (ADR/runbook acceptance `2ae3fcf`).
- Files touched:
  - .github/workflows/ci.yml
  - README.md
  - docs/architecture.md
  - docs/capability-matrix.md
  - docs/pre-launch-gap-analysis.md
  - scripts/check_schema_chain.py
  - scripts/run_gate_a_eval.py
  - scripts/run_mode_deterministic_eval.py
  - src/agent/catalogue.py
  - src/agent/modes.py
  - src/agent/runtime.py
  - src/api/reminders.py
  - src/bot/handlers.py
  - src/bot/reminder_actions.py
  - src/bot/turns.py
  - src/commands/base.py
  - src/evaluation/gate_a.py
  - src/main.py
  - src/memory/memory_store.py
  - src/memory/reminders.py
  - src/memory/store.py
  - src/schema.py
  - src/tools/toolsets.py
  - tests/fakes.py
  - tests/sql/app_schema_version.sql
  - .scratch/modular-modes/evals/
  - .scratch/modular-modes/proposals/018-independent-verification.md
  - .scratch/modular-modes/proposals/019-independent-probes/
  - .scratch/modular-modes/proposals/019-independent-verification.md
  - .scratch/modular-modes/proposals/issue04-coaching-store-design.md
  - evals/coach/
  - evals/recommender/
  - evals/reflect/
  - migrations/018_coaching_programs.sql
  - migrations/019_proactive_delivery_budget.sql
  - src/agent/coach.py
  - src/agent/recommender.py
  - src/agent/reflect.py
  - src/api/coaching.py
  - src/coaching.py
  - src/memory/coaching.py
  - src/memory/proactive.py
  - src/mode_readiness.py
  - src/scheduler/coaching.py
  - src/tools/coaching.py
  - src/tools/recommender.py
  - src/wellbeing.py
  - tests/sql/assert_018_coaching_programs.sql
  - tests/sql/assert_019_proactive_delivery_budget.sql
  - tests/test_coaching_application.py
  - tests/test_coaching_delivery.py
  - tests/test_coaching_state.py
  - tests/test_coaching_store_contracts.py
  - tests/test_mode_candidates.py
  - tests/test_recommender.py
  - tests/test_reflect.py
  - tests/test_reminder_budget.py

- Protected edits: migrations/018_coaching_programs.sql; migrations/019_proactive_delivery_budget.sql.
  No config, .env, deployed schema/data, push, participant pin or external message changes.
- Independent migration reviews: proposals/018-independent-verification.md and
  proposals/019-independent-verification.md (exact hashes/probes retained). Root full **41-file CI
  SQL chain passed** on a new local PG15 DB amigo019_full_2c4c1974ae; all assertions through019,
  schema19 predecessor/gap checks passed; Activation forced-interleave/30 trials/155 calls passed.
  Independent019 proves atomic refused reschedule/Later leaves original Reminder, Task version,
  outbox and receipts unchanged; eight parallel reservations admit4/refuse4; mixed Coach/Reminder
  budget race admits4/refuses1. Legacy attempted/accepted slots survive cancellation.
- Coach: one owned versioned Program, exact-draft one-use participant button activation (model
  activation Tool only displays preview), fixed14-day term, explicit bounded extension, participant
  progress, weekly choice, pause/stop, owned Program inspection/export/delete. Shared budget
  transactions cover Reminder scheduling/reschedule/Later/Activation/direct writes and Coach;
  unsent cancellation releases capacity, consumed/uncertain delivery remains counted. Refusals
  produce clear Tool/callback/API responses. No silent dropping of existing commitments.
- Outbox: selected weekdays/time, DST validation, <=15min late window, quiet hours, one Coach/day,
  one missed follow-up then silence including reviews; authenticated return resets wait.
  Canonical Activation/grant/consent/state/lease checks precede dispatch, uncertain outcomes never
  retry. Program delete cancels unused queued work; consumed content-free accounting remains.
- Provisional choices: existing over-budget commitments remain explicit legacy debt, reducing
  Coach capacity; new requests refuse atomically. Default4 comes from existing profile schema,
  never a model/caller limit. Program term14x24h; weekly review replaces selected check-in, DST gap
  skipped/earliest fold only. Owner review required before enabling trial admission.
- Reflect candidate: isolated history/context, no ordinary writes/Memory/Mood/CBT/exercises,
  default-deny per-Turn readiness and separate consent, fresh-resource metadata checks with empty
  default registry and static general emergency fallback. No stale or invented contact details.
- Recommender: fictional laundry comparison only, labelled simulated weather, no location/live
  source/saved preference/transaction; dryer/flexible-postpone/urgent-alternative order tested.
- Privacy facts: whole-account rights/retention operations and qualified wellbeing approval remain
  missing. Coach/Reflect real admission defaults OFF. Program-only rights endpoint explicitly
  retains conversation Messages/provider copies; no broader privacy promise is made. Trial demand,
  moderated usability, qualified review and participant outcomes are not invented.
- Model evidence: fictional development cases only. Claude Coach/Reflect passed; laundry first
  failed verbosity, then passed after prompt fix. Ollama Reflect passed; laundry failed Tool args;
  Coach output exposed a brittle goal-vs-habit expected phrase, corrected in authored suite (the
  original failed artifact remains). None constitutes a passing provider fallback/allowlist.
- Sole full Gemini batches deferred until Phase6 shared execution sources stop changing, so final
  per-Mode evidence is not knowingly stale. Modes stay Planned until those batches pass; candidate
  runner uses only new InMemoryStores/synthetic grants, never modifies application definitions, and
  labels artifacts candidate_eval (cannot certify release or fallback). Gemini requests so far0.
- Validator correction: punctuation-only response assertions match literal punctuation, rather
  than the empty normalized string; stop/no-question case now meaningful. All semantic criteria
  retained. New modules added to fingerprint closure; currency tests untouched. GateA certification
  still absent, no fabricated artifact or human approval.
- Validation: **1142 passed in 10.40s**; Ruff **All checks passed**; scheduler smoke
  **in-memory APScheduler reminder fired through channel**; diff whitespace clean.
  Includes Daily golden/schema, currency, all52 candidate scripted cases, ownership/readiness,
  24 application approval/rights tests, 56 Reminder budget tests and32 coaching delivery tests.
- Extra corrections: API availability respects admission guard; model evidence currency binds
  guard identity. Consent country ASCII validation mirrors SQL. Worker checks mutable readiness
  before/after awaited policy, immediately before durable dispatch and provider send; post-mark
  kill sends nothing, retains uncertain capacity. Weekly controls include all four choices.
- Backend foundation committed separately from dashboard records access (following UI slice).
  Full provider batches remain deferred until Phase6 source closure stabilizes, as above.

## Phase 5 follow-up — current-profile quiet hours and shared Coach day cap

- Parent: 402bed5; this commit fixes the four reproduced travel-timezone failures.
- Files: migrations/019_proactive_delivery_budget.sql (protected); src/memory/proactive.py;
  src/scheduler/coaching.py; tests/test_coaching_delivery.py;
  tests/sql/assert_019_proactive_delivery_budget.sql; 019 independent verification and retained
  travel probe/verification under proposals/.
- Program timezone controls cadence; current profile timezone controls quiet hours. Coach cap
  applies across Programs and deleted Program references, including accepted/uncertain delivery;
  dispatcher rechecks current budget and timezone. Unsent cancellation releases capacity.
- Evidence: 1151 tests passed in 10.65s; Ruff clean; diff whitespace clean. Original SQL failed
  travel regression; fresh full 41-file CI SQL chain passed. Independent reviewer reran retained
  atomic rollback, legacy debt, fencing and mixed concurrency probes; PASS at migration SHA256
  4c6c0f0ca24e6fd1a65f987d0686c7819e3222bce91c1bde48d189e34b94c781.
  Assertion SHA256 b8d181f65df9cfcc2d62bba28d999d3b16cda524214b1b096a6971a0f99b5993.
- Gate A currency/Daily golden included in full suite; production certification still absent.
  No new provisional policy, admission enablement, deployment or external data changes.

## Phase 5 follow-up — Coaching records dashboard

- Prior fix committed 5bff2b4. This slice: web/src/components/CoachingRecords.jsx,
  CoachingRecords.css, AppShell.jsx; proposals/coaching-records-ui-verification.md and fictional
  desktop/mobile captures/results under .impeccable/review/coaching-records/.
- Owned Program history, JSON export, explicit scoped deletion confirmation, uncertain-delete
  refresh, loading/empty/error recovery. Conversation Messages/provider copies explicitly remain.
- Web ESLint zero warnings; Vite8.3.5 build passed (1988 modules). Local fictional API/auth browser
  checks passed at 1440px and390px: history/export/delete/retry, no overflow or browser errors.
  Independent visual/source review: SHIP, no material findings; skill detector returned [].
- Protected files: none. Backend remains 1151 passing/Ruff clean; no Turn source changes in this
  UI slice, Gate A currency inputs unchanged. Existing absent release certification not replaced.
- Preserve incumbent dashboard design. Coach admission remains OFF; no broader privacy promise.

## Phase 6 — Issue07 delegation triage

- Parent48a164f; files: issues/07-delegate-between-modes.md and
  proposals/phase6-07-delegation-triage.md. Protected files: none.
- Provisional — owner review: Do Not Build an inter-Mode delegation graph. Existing owned context
  providers are an available mechanism, not approval to expose Daily Tasks to Coach. Confirmed
  handoffs already cover ordinary Task/Reminder actions with isolated Sessions and crash replay.
- Evidence: routing/candidate/Coach application tests89 passed1.99s; latest combined worktree
  full suite1305 passed10.51s, Ruff/scheduler smoke passed. Daily golden and111 currency tests pass.
  No code in this documentation slice changes Gate A inputs; release certification remains absent.
- Open: recurring participant job, concrete failing existing flow, approved data contract and
  measured benefit. No demand/trial evidence or permanent owner decision manufactured.

## Phase 6 — confirmed suggestions, explicit Memory, declared durable workflows

- Parent5636e80. Backend slice implements Issues05/06/08 under provisional owner-review records.
- Files touched:
  - .github/workflows/ci.yml
  - .scratch/modular-modes/proposals/020-independent-probes/amigo-review020-extra.sql
  - .scratch/modular-modes/proposals/020-independent-probes/amigo-review020.py
  - .scratch/modular-modes/proposals/020-independent-verification.md
  - .scratch/modular-modes/proposals/021-independent-probes/amigo-review021.py
  - .scratch/modular-modes/proposals/021-independent-review.md
  - .scratch/modular-modes/proposals/phase6-05-confirmed-mode-suggestions.md
  - .scratch/modular-modes/proposals/phase6-06-store-backed-memory.md
  - .scratch/modular-modes/proposals/phase6-08-durable-workflows.md
  - .scratch/modular-modes/proposals/phase6-chain-verification.md
  - README.md
  - docs/architecture.md
  - docs/capability-matrix.md
  - docs/pre-launch-gap-analysis.md
  - evals/memory/v1/README.md
  - evals/memory/v1/cases.json
  - migrations/020_durable_memory.sql
  - migrations/021_confirmed_mode_suggestions.sql
  - scripts/check_schema_chain.py
  - src/agent/catalogue.py
  - src/agent/modes.py
  - src/api/coaching.py
  - src/api/memory.py
  - src/bot/handlers.py
  - src/bot/turns.py
  - src/cli.py
  - src/evaluation/gate_a.py
  - src/main.py
  - src/memory/durable.py
  - src/memory/memory_store.py
  - src/memory/store.py
  - src/memory/suggestions.py
  - src/memory_service.py
  - src/mode_suggestions.py
  - src/schema.py
  - src/tools/memory.py
  - src/workflows.py
  - tests/fakes.py
  - tests/sql/app_schema_version.sql
  - tests/sql/assert_020_durable_memory.sql
  - tests/sql/assert_021_confirmed_mode_suggestions.sql
  - tests/test_memory_retrieval_eval.py
  - tests/test_memory_service.py
  - tests/test_memory_store.py
  - tests/test_mode_suggestions.py
  - tests/test_workflows.py

- Protected edits: migrations/020_durable_memory.sql, migrations/021_confirmed_mode_suggestions.sql.
  No .env, config defaults, deployed schema/data, participant pins, push or external messages changed.
- Evidence: **1313 tests passed11.07s**; Ruff All checks passed; diff clean; scheduler smoke fired
  through in-memory channel. Includes Daily golden/Tool-schema and111 Gate A currency tests.
  Added reachable modules to fingerprint; currency tests unmodified. Release Gate A artifact
  remains absent; candidate tests do not certify production or a provider fallback.
- Fresh full45-file local CI SQL chain passed at schema21, all missing-chain/predecessor guards
  passed, Activation forced-interleave/30trials155calls passed. Independent020/021 reviews and
  frozen hashes/probes retained; combined final reviewed020 hash273f33cc… and0217c515d31… proven.
- Suggestions: default OFF, explicit current-job rules, no sentiment/silence/Task-behavior signals,
  one offer per owned open Daily Session, persistent stop preference, no carried text/history or
  target Turn on confirmation. Same canonical entry path for both channel types; current grants,
  catalogue/readiness and single-use expiry checks. Default-deny per-Turn clearance seam remains
  unimplemented for real admission; lexical crisis suppression does not certify safety detection.
  Decisions23/28 release/friction evidence still missing.54 focused tests, SQL8create→1/8confirm→1.
- Memory: all-three Store parity; default-deny application semantic eligibility/readiness plus
  database admissionOFF; max5 enabled owners globally serialized, paused owners counted. Exact
  owned preview confirms payload/settings/item version; first opt-in atomic. Corrections/sharing/
  reconfirmation versioned;90/180day aging, explicit validity, goal completion/cancellation, separate
  learning/use pauses, max3 scoped relevant items across a Turn, content-free uses, complete scoped
  JSON/CSV and Forget/ForgetAll purge. Candidate plaintext process-local only, bounded cache with
  timer cleanup and concurrent-limit regression. No registered Daily Memory Tool/context provider.
  Optional proposal-only Tool cannot confirm; channel receipt offers Edit/Forget/Undo. Inspector
  API complete; dashboard UI follows separately. Whole-account/provider/backup deletion unverified.
- Independent020 findings fixed: NULL validation, optimistic settings version, pre-ledger guard.
  Unicode Python/PG digest parity and6 concurrent opt-ins→5pass1refuse proven. Seventeen authored
  retrieval fixtures passed exact ID sets; this does not establish generalized95% retrieval or
  prohibited-content classification. Decision26 demand, privacy/eligibility review, five-person
  usability and14-day trial remain open. Memory admission stays OFF.
- Workflows: Coach-only immutable v1 declaration and owned metadata inspection reuse018/019
  Program/outbox/Command records.16 new tests replace workers after enqueue/claim/dispatch/accepted
  on both channel paths; occurrence preserved, stale token fenced, uncertain provider send never
  repeated. No generic/external engine or persisted per-Program definition-version binding; only
  current v1 exists, future changes require explicit binding/migration decision. No trial evidence
  or arbitrary Tool workflow guarantee invented.
- Sole final Gemini batches remain deferred until execution sources freeze; full Claude/Ollama
  development suites retain failures. New Modes remain Planned until required provider evidence.

## Phase 6 — Memory Inspector dashboard

- Backend0be20bb; files web/src/components/MemoryInspector.jsx, MemoryInspector.css, AppShell.jsx;
  proposals/memory-inspector-independent-verification.md + retained fictional browser probes;
  .impeccable/review/memory-inspector/ desktop/mobile/first-opt-in captures, exports and results.
- Complete versions/states/provenance/use history; explicit exact previews + first-item opt-in,
  corrections/reconfirmation/Mode sharing, independent/master pauses, lifecycle controls,
  complete JSON/CSV with formula escaping, scoped Forget/ForgetAll. Hash links open canonical
  Inspector. Saving remains OFF; inspection/rights controls available. Stale/uncertain mutation
  locks changes/export until refresh. No provider/backup/whole-account erasure claim.
- ESLint zero warnings; Vite8.3.5 build passed1990modules (existing >500kB chunk warning retained).
  Single detector pass changed3targets returned[]. Desktop1440/mobile390 fictional stub behavior
  passed: consent/version/history/filter/export/pause/forget/stale recovery; no overflow/pageerrors.
- Fresh independent finish review found focus-discovery bug; fixed Edit/Forget heading focus without
  stealing text-input focus. Targeted corrective checks passed both viewports; final reviewerSHIP.
  No additional detector or open-ended UI review loop. Incumbent oat/sand, Fraunces/Inter preserved.
- Protected files:none; no Turn source changes in this UI slice. Latest full backend1313passed,
  Ruff/smoke passed; Gate A currency inputs unchanged by these UI files, release certification absent.
- Open: actual eligibility/privacy/retention/demand/usability/trial evidence, as backend record.

## Phase 6 follow-up — exact Memory Message provenance

- Parent20724b4; files src/memory/store.py, memory_store.py, tests/fakes.py,
  src/tools/memory.py, tests/test_memory_service.py. Protected files:none; no migration.
- Optional unregistered proposal Tool now reads latest owned user Message metadata through a
  dedicated Store API, checks both Session/Message owner and Mode, and uses its actual recorded
  date/channel. Transcript DTO remains unchanged. Missing date refuses instead of inventing one.
- Evidence: **1323 tests passed38.28s**, Ruff clean, diff clean. Past-date/missing-date and
  cross-owner metadata query regressions pass; Daily golden/schema and111 currency pass.
  Removed formatter-only Store churn after AST-equivalence check; only new methods remain.
- Gate A source inputs changed; no release artifact certified. No Memory admission enablement.

## Phase 5/6 model iteration follow-up — bounded offline profile and observed reply defects

- Parent11e923d; files src/agent/runtime.py, src/agent/coach.py, src/agent/reflect.py,
  tests/test_dev_models.py. Protected files:none.
- Actual unbounded Ollama first cases took64–72s and produced excessive hidden thinking; original
  partial runs cancelled explicitly and preserved unchanged, with separate cancellation manifest.
  Development-only public OllamaModel defaults: max_tokens512, reasoning_effort none, timeout60.
  Production provider defaults unchanged. Mock outgoing-body test verifies SDK mapping to
  max_completion_tokens512/reasoning_effort none/timeout; first bounded Coach case17.7s.
  Primary protocol reference: https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx
- Full Claude suites: Coach40/48, Reflect37/60, Recommender28/48 case executions pass; no fallback
  certification. Original artifacts retain failures, including wording-sensitive assertions,
  excess sentence count and redundant draft+approval preview calls. No assertions weakened.
- Coach prompt now avoids redundant activate_program immediately after draft_program and avoids
  pitching a Program after a clinical refusal unless separately requested. Reflect prompt now
  enforces existing six-sentence contract. Revised cases retained separately; no old artifact
  rescoring. Daily instructions/Tools byte-identical.
- Evidence: full1323passed38.28s; Ruff/diff clean;111 Gate A currency and Daily golden pass.
  Execution source changes invalidate older evidence. Final sole Gemini batches follow this
  source freeze; candidates remain Planned unless all required model/release evidence qualifies.

## Phases 4–6 review fixes — owner stop and baseline

- Owner review scope through0be20bb; subsequent authorized completed source commits20724b4,
  11e923d andb2c824f retained. get_memory_source_message already committed11e923d across3Stores;
  Ruff E501 fixed before this instruction. Latest full1323passed/Ruffclean, scheduler smoke passed.
- Stopped new Phase6 work and every model job immediately. No Issue09 repository document/code
  exists. Temporary design draft not promoted; no deploy/Supabase/.env/push changes.
- Preserved original full Claude scores (Coach40/48,Reflect37/60,Recommender28/48), revised case
  outputs and unchanged partial Ollama/Gemini artifacts. Separate cancellation manifests identify
  owner stop, rather than silently changing running artifacts to passing/completed evidence.
- Gemini totals at stop:16requests,27,572known inputtokens,5,644known outputtokens;15ok/1error,
  one request with unknown token counts. Coach final batch partial only; other2never started.
  No model/fallback/release certification; no further model requests during review fixes.
- Review findings and both Owner decisions blocks read fully. All1–20 tracked for this repair
  series. Handoff/017, budget/019 and Memory/020 changes isolated in managed checkouts; each SQL
  change requires independent review before its separate develop integration commit.

### Review fix1 — topics-off startup remains available

- Files src/channels/telegram.py, tests/test_channel_conversations.py, README.md,
  docs/architecture.md, docs/capability-matrix.md, docs/adr/0003-mode-topics.md. Protected:none.
- Topics off now warns and uses in-chat Mode commands in production and development. Refuse only
  topics-on plus user-created-on; unknown user-created flag warns. Development getMe failure
  warns without provider details and leaves command mode available; production lookup failure
  still refuses. grant_mode.py shares this same initializer.
- Full1326passed20.31s; focused channel/operator/currency checks passed; Ruff/diff clean.
  Daily golden/schema and111 currency tests unchanged. Gate A evidence remains uncertified.
  SQL unchanged in this fix; combined full-chain verification follows SQL repair integrations.

### Review fix5 — 019 profile/budget lock order

- Author4f3bf65 integrated separately; files migrations/019_proactive_delivery_budget.sql
  (protected), tests/test_migration_lock_order.py, proposals/review-fix05-lock-order-verification.md.
- update_reminder_budget takes user_profiles FOR KEY SHARE before the advisory budget lock.
  Inline function parser now checks all row-lock modes and017–019/five proactive entry points.
  Budget policy unchanged in this slice; owner proactive-only decision follows separately.
- Independent cbt_selector fresh45-file CI SQL chain PASS at019hash4638f74e…;157lock-order tests
  passed0.27s/Ruffclean. Root full1336passed20.66s, Ruff/diff clean, currency/golden included.
  No production schema/data/credentials changed; release Gate A certification absent.

### Review fix13 / owner decision — Memory off forgets all and frees slot

- Author545a740 integrated separately. Files migration020 (protected), assert020, durable.py,
  all3Stores, MemoryService/API/Inspector JSX/CSS and Store/service tests; independent record
  proposals/review-fix13-memory-withdrawal-verification.md.
- Explicit owned disable deletes all Memoryversions/tombstones/claims/uses/oldreceipts, resets
  enabledfalse and consent, frees trial slot. Re-enable starts fresh with first-item consent.
  Stale confirmations cannot restore content; conversation Messages/provider copies remain.
- Independent fresh45-file SQL chain PASS at020hashccec4ac4…;73Store/service/APItests passed,
  author90focused passed; ESLint/build/Ruffclean. Rootfull1346passed21.46s/Ruff/diffclean;
 111currency/Daily golden included. Release Gate A certification absent; no live admission.

### Review fix16 — shared transcript DTO parity

- get_memory_source_message was already committed11e923d with E501 fixes. Remaining16 change:
  tests/fakes.py transcript now matches real/InMemory role/content/created_at only; detached rows.
  New tests/test_session_message_contract.py verifies shape, detachment and separate provenance API.
- Focused transcript/Memory/currency tests passed; Ruff/diff clean. Prior full1346passed;
  next combined full suite includes these two new cases. Protected/SQL files:none.
  Daily prompt/Tool schema unchanged; no model/Gate A certification fabricated.

### Review fix2/15 — maintenance failure isolation

- Files src/maintenance.py, src/main.py, src/cli.py, src/conversations.py,
  src/evaluation/gate_a.py, tests/test_mode_maintenance.py. Protected/SQL:none.
- Independent maintenance stages and conversation/handoff rows continue after errors; error logs
  carry stage and exception class only. Canonical conversation closes even if provider close fails.
  Failed readiness disables Coach admission. Cancellation propagates. Memory prune is isolated.
- Full1353passed20.53s; focused maintenance/currency116passed12.63s; Ruff/diff clean.
  Added reachable maintenance module to fingerprint closure; currency checker unchanged.
  Daily golden/schema included; no current release Gate A certification. SQL unchanged here.
- Evidence correction for fix13: independent73pytest count used default import mode and may have
  resolved main checkout; exclude that count from isolated review evidence. Independent frozen
  45-file SQL chain, source/API/UI review, author90focused and root1346full remain valid.

### Review fix12 — schema21 cutover runbook

- Files docs/runbooks/mode-schema-21-cutover.md, README.md,
  proposals/topic-spike-runbook.md. Protected/SQL:none.
- Owner-run only: zero confirmed handoffs and valid timezone preflights; maintenance window;
  017→021 in one psql session with version checks; immediate matching deploy. Topics may remain
  off; if enabled user-created threads must be off. Android remains untested. No execution here.
- Documentation checked against schema21/CI migration order. Latest full1353passed20.53s,
  Ruff/diff clean; currency unchanged. Final combined SQL chain follows remaining SQL fixes.

### Review fix4 — terminal unavailable recovery claims

- Author4068b5f; protected017 and assert017, modes.py/all3Stores, handoff terminal/Store tests,
  independent evidence proposal. Unavailable owned claim records terminal reason/time; stale
  leases cannot finalize; failed rows leave LIMIT25 recovery queue and cannot replay/complete.
- Independent usage_gate fresh45-file CI chain PASS at017SHA745aab3d…; ownership/livelease/
  stale-token/25blocked→26th queue drain checks PASS. Reviewer cluster stopped.
- Root full1362passed20.34s; Ruff/diff clean,111currency/Daily golden included. Author scheduler
  smoke passed. Two-attempt cap/one notice follow separately in fix3. No release certification.

### Review fix14 — Forget digests, stale claims and retention policy

- Author3af05ab; protected020/assert020, all3Stores, MemoryService/durable and tests;
  proposals/memory-retention-policy.md explicitly records retained version policy and unverified
  operational7dayactive/30daybackup Forget propagation requirement. Admission remains off.
- Forget deletes all owned confirmation claims and nulls every owned receipt payload_hash,
  including current Forget; hash-bearing replay results scrubbed. Old write keys cannot replay;
  safe Forget retry returns status only. Prune removes consumed/expired claims even admission-off.
- Independent dev_runtime fresh45-file CI SQL chain and ownership/hash/replay/history probes PASS
  at020SHA83c26e01…; reviewer cluster stopped. Rootfull1372passed21.08s/Ruff/diffclean;
 111currency and Daily golden included. No new privacy notice promise or release certification.

### Review fix17 — minimal escaped Memory context

- Author9bf46a9; MemoryService and retrieval tests only, no protected/SQL files.
- Saved Memory renders only text/category/fixed purpose. JSON escapes angle brackets so Memory
  cannot terminate its enclosing prompt block; ids, provenance and lifecycle fields omitted.
- Root172service/retrieval/currency passed11.97s; Ruff/diff clean. Latest full1372passed;
  Daily golden/schema unchanged. Gate A source fingerprint changed; no release certification.

### Owner budget decision — proactive messages only

- Authorba832ce; protected019/assert019, proactive/all3Stores, Reminder scheduler/Tools,
  auxiliary evals/gate_a/v1/budget-regressions.json, test_budget_gate_a and related tests/docs.
- Requested Reminders, Later and Activation tests neither reserve nor refuse proactive capacity.
  Coach plus recovery summaries reserve capacity; recovery dispatch/accept/uncertain fenced and
  cannot replay. Uncertain delivery retains capacity. Legacy Reminder reservations excluded.
- Independent cbt_selector fresh45-file CI SQL chain/source/3Store parity PASS at019SHA9377ef24…;
  zero-budget requested paths/recovery fence/uncertain-capacity checks PASS; cluster stopped.
- Root full1352passed21.48s/Ruff/diffclean. Removed obsolete budget-refusal tests replaced with
  requested-reminder/recovery invariants. Two auxiliary scripted Daily Gate A scorer cases pass;
  original60case suite, Daily instructions/Tool schema/goldens and111currency unchanged.
  No real model calls or Gate A release certification.

### Review fix7 — skip unchanged Mode selectors

- Files src/bot/modes.py, tests/test_mode_routing.py; protected/SQL:none.
- Compare owned Session selector before set_active_mode for fixed Mode Sessions and command
  control Session. Ordinary Daily/Coach Turns and repeated commands avoid writes/global lock.
  Runtime entitlement remains checked on every Turn; revoked grants still refuse.
- Threaded+command regressions/currency163passed12.44s; fullRuff/diffclean. Latestfull1352passed;
  no changes to Daily prompts/Tools/currency checker and no release certification.

### Review fix8 — no unpaired/denied bootstrap topics

- Files channels/telegram.py, conversations.py, bot/handlers.py, bot/pairing.py and channel/pairing
  tests. Protected/SQL:none. Removed in-memory bootstrap creation. Unpaired threaded deliveries
  use an explicit incoming address or omit delivery; never send unthreaded/create resources.
  Denied chats do not invoke canonical resolver. Successful pairing persists incoming conversation
  as canonical Daily before response, or creates one durable Daily if no incoming address.
- Pairing/channel/currency163passed10.74s; routing/channel/pairing102passed4.14s; Ruff/diffclean.
  Added successful adoption/no-topic and denied-chat regressions. No provider/network calls.
  Latestfull1352passed; current source invalidates prior Gate A release evidence.

### Review fix18 — Memory lock graph and private validation

- Author001dcab; protected020/assert020, durable.py, MemoryStore and Store/lock-order tests.
- Profile FOR KEY SHARE precedes owned advisory lock; global admission lock only for new opt-in.
  Scope order uses C collation; malformed input and unexpected RPC errors return clean errors.
- Independent dev_runtime fresh45-file SQL PASS at020SHAe5e6a395…; six concurrent optins→5admitted,
  1cap; enabled save0.024s while admission lock held; profile-delete interleave acquired no owned
  advisory while waiting. Unicode scope digest parity and private error probes PASS; cluster stopped.
- Root221Memory/lock/currency tests passed12.18s; fullRuff/diffclean. Latestfull1352passed;
  no actual model/Gate A certification or live admission. Final SQL chain follows021 repairs.

### Review fix3 — bounded handoff execution and transcript

- Author3b5ed90; protected017/assert017, handoffs.py, turns.py/ContextBuilder, handlers callback
  messageid, modes.py/all3Stores, bounded/terminal tests and independent proof proposal.
- At most2 claims; second failure terminal. ensure is inside failure handling. Carried input and
  reply append once per role under lease fence; only current carried input excluded from history.
  Terminal notice has durable at-most-one send attempt; crash after notice claim can lose notice,
  never duplicate it. Owned stale buttons removed. Recovery isolates each row.
- Independent usage_gate fresh45-file SQL chain + owner/token/role/lease/content/dedup/thirdclaim/
  notice fences PASS017SHA09e0a285…;42focusedPASS2.54s. Rootfull1401passed22.69s/Ruff/diffclean;
 111currency/Dailygolden included. Author scheduler smoke passed. No release certification.

### Review fix9 — deterministic Reflect safety routing

- Files wellbeing.py, bot/modes.py, turns.py, both eval runners, Reflect deterministic fixture
  and tests. Protected/SQL:none; wellbeing already in source fingerprint closure.
- Known immediate/explicit/ambiguous English statements use static CrisisRegistry responses
  before Reflect admission, transcript persistence or model access. Empty/stale resource registry
  supplies general local guidance and asks country; never infers location or invents contacts.
  Ordinary disappointment/idioms and explicit negation remain ordinary. Same route in command,
  threaded and direct orchestration paths; default Reflect admission still off.
- These bounded routing rules are not clinical assessment or comprehensive detection; qualified
  wellbeing review and other consent/privacy gates remain mandatory before enabling Reflect.
-165Reflect/candidate/currency tests passed11.36s; Ruff/diffclean. Three fixture safety cases now
  require application output without model messages. Runners score actual result.output, including
  static replies. No historical artifact rescoring/model requests/Gate A release certification.

### Review fix11 / 017 — per-participant conversation serialization

- Authord0cf36b; protected017, reproducible SQL probe and independent review proposal.
- Mode conversation writes serialize per owner rather than global Daily. Guarded endpoint upsert
  rejects a concurrent foreign owner instead of reopening their row. Existing backfill already
  covers every Session, including closed ones; independent pre017 seed verifies both paths.
- Independent usage_gate fresh45SQL chain PASS017SHA9aa3d1bc…; ownerA lock blockedA whileB
  completed; forced two-owner absent-endpoint race rejected loser without foreign mutation;
  close/reopen/closed-owner probes PASS. Root303conversation/lock/currency passed11.32s;
  Ruff/diffclean. Latestfull1401passed; no Gate A release certification or live migration apply.

### Review fix19 / pause — stale Memory state reply

- Author6833721; handlers.py and MemoryService regression only; protected/SQL:none.
- /memory pause catches stale-version conflict and asks participant to refresh current state;
  keeps current conversation and never calls model or exposes RPC details.
- Root67Memory/pairing passed2.45s; Ruff/diffclean. Latestfull1401passed; currency/source
  certification remains absent. Atomic suggestion confirmation follows separately.

### Owner progress decision — explicit same-day cancellation

- Author096ba32; protected019/assert019, proactive.py, localStore mirrors and delivery tests.
- Dispatch checks participant-reported progress on Program-local day before generic version
  mismatch, records progress_logged_today. Pause, edit and consent keep distinct reasons.
- Independent cbt_selector fresh45SQL chain + Kiritimati-midnight/yesterday/foreign-owner/program/
  helperprivilege probes PASS019SHA5e3e6b30…; root180Coach/currency passed11.51s/Ruff/diffclean.
  Latestfull1401passed; no model/Gate A certification. No participant-requested Reminder change.

### Owner suggestions decision — explicit opt-in

- Author27128bf; protected021/assert021, local suggestion default, owned StrictBool preference API,
  main router, DashboardView and new ModeSuggestionPreference JSX/CSS; tests.
- Preference defaultsfalse locally/SQL. Dashboard checkbox allows explicit opt-in/out, disabling
  pending offers on opt-out. No release gate bypass. UI error disables writes until refresh.
- Independent cbt_selector fresh45SQLchain/owner/defaultoff/preoptinoffer/disablepending PASS at021
  SHAb9e8e9ae…; root168suggestion/currencyPASS10.56s +2preferenceAPItestsPASS2.50s; Ruff,
  ESLint/build/diffclean. Buildexisting>500k chunkwarning. UI source-reviewed, no browserclaimyet.
- Reflect follow-up98e8d66 fixes independent disclosure-negation finding; reviewer reproduced
  correction and41testsPASS2.23s. No claim of clinical review/comprehensive detection.
  Latestfull1401passed; release Gate A evidence absent and all candidates remainPlanned.

### Review fix2 / Coach rows — cleanup failures also isolated

- Author330e309; scheduler/coaching.py, delivery tests; protected/SQL:none.
- Each Program reconcile and delivery claim isolated, including malformed claims and failed error
  cleanup. Content-free warning labels. Later eligible Program/check-in still reconciles/sends.
- Root50deliverytestsPASS0.14s; author74focusedPASS2.64s; fullRuff/diffclean.
  Latestfull1401passed,168currency/suggestion checks pass; no Gate A release certification.

### Review fix11 / application boundaries

- Files conversations.py, channels/telegram.py, bot/modes.py, tools/coaching.py,
  api/coaching.py, grant_mode.py and conversation/channel/operator/Coach tests. Protected/SQL:none.
- Cross-process ensure loser closes only its own created resource and returns persisted winner,
  even provider cleanup fails. Topics-off ignores stale thread for sends. Unexpected Mode/operator
  failures log exception type only. Naive operator expiry rejected before mutation. Program Tool
  and workflow API ids typedUUID; values normalized to strings at Store/command boundary.
-103focusedPASS2.58s; fullRuff/diffclean. Cleanup fail/success, no thread echo, timezone rejection
  and UUID schema tests included. Same-process creation locks retained. Latestfull1401passed;
  final combined suite/currency follows pending019/021 and eval rubric fixes.

### Review fix11 / Coach delivery boundaries

- Author340984a; proactive.py, scheduler/coaching.py, delivery tests; protected/SQL:none.
- Activation and final durable admission precede topic creation. Denied Activation/progress never
  creates a conversation. Provider creation failure after durable dispatch mark becomes uncertain
  and does not replay. Local quiet hours parse datetime.time including seconds, matching SQL TIME.
- Root81Coachapp/deliveryPASS2.89s; authorisolatedfull1328PASS20.58s and scheduler smokePASS.
  RootfullRuff/diffclean; prior independent review of application boundary3811bc8 found no blocker,
  87focusedPASS2.91s. Latestfull1401passed; final combined suite follows candidate rubric repair.

### Review fixes10/20 — candidate behavior and semantic rubrics

- Files Coach instructions/Tools/controller, gate_a.py/new evaluation/meaning.py, three candidate
  cases+deterministic fixtures, candidate-meaning/Coach application tests. Protected/SQL:none.
- Removed model activate_program Tool; draft shows approval once, /program re-shows it model-free.
  Only participant callback can activate. Coach bounded8sentences, clinical refusal avoids Program
  upsell/clinical treatment. Actual callback ownership/approval tests preserved.
-52candidate IDs now coach-/reflect-/recommender-; original Daily60case ga IDs, thresholds,
  instructions/Tool schema/goldens and currency test unchanged. Full scripted52cases pass.
  Required/forbidden semantic concepts accept paraphrases/contractions, bind refusal to its action,
  reject affirmative clinical/safety claims, preserve stop/postpone polarity. Meaning source added
  to fingerprint closure. This is a bounded deterministic rubric, not general NLU or certification.
- Independent dev_runtime review found three rubric defects, then two unsafe paraphrases; all fixed
  with actual-case fullscore regressions. Final independent172meaning/candidate/Daily/currencyPASS
  11.63s, no remaining scoped blocker. Root1476fullPASS22.17s; E501 follow-up wraps only literal
  strings, Ruff/diff nowclean. No existing test thresholds lowered or artifact rescored.
- Correct provider evidence: historical complete ClaudeCoach40/48,Recommender28/48,Reflect37/60
  at earlier source, not passing certification. Partial cancelled Ollama/Gemini artifacts unchanged.
  No model calls during repair; Gemini total remains16requests/27,572knowninput/5,644knownoutput,
 15ok/1error,1unknownusage. All3Modes remainPlanned until fresh required Gemini suites pass.

### Review fix14 / policy attribution clarification

- Corrected retention policy attribution: implementation uses owner-permitted documented-policy
  option, pending owner review; owner did not independently select this implementation policy.
  Decision13 explicitly preserves superseded version history and applies7day/30day deletion windows
  afterForget. No code, notice, production data or privacy promise changed. Diffcheckclean.

### Review fix19 — atomic logical Mode opening and provider retry receipt

- Author9fd285c; protected021/assert021, suggestions.py/all3Stores, ModeSuggestionController,
  suggestion tests, proposal/suggestion-opening-receipt.md.
- Confirmation rechecks owned source/newestDailycontrol/target, opt-in, grant and pending Handoff/
  Coach approval. Same transaction creates/reuses targetSession and selects all owned control
  pointers. Service SELECT revoked. No carried content or model call. Provider conversation ensure
  follows logical DB opening with5minute token-fenced claim/release/complete receipt; completed
  buttons cannot reopen or override later manual switch/newerDailySession. Notice follows completion.
- Referenced Session locks sorted before offer lock to avoid target/control FK cascade inversion.
  Independent cbt_selector fresh45CI SQL chain/helper-first concurrent DELETE/singleuse/revokedgrant/
  manualswitch PASS021SHA12d607bf…; author delete-first interleavings PASS.83focusedPASS2.29s.
- Rootfull1512passed22.21s/Ruff/diffclean,111currency/Dailygolden included. No Gate A release
  certification; no provider/Supabase access. Final whole-chain proof follows production recovery
  integration checks. External endpoint creation cannot be atomic with Postgres; receipt fences retry.

### Review fixes2–4 / production recovery integration

- Files src/main.py, src/handoffs.py, tests/test_handoff_production_recovery.py; protected/SQL:none.
- Production maintenance previously used its own execution scan and omitted durable failed-notice
  scan. Now execution/notice scans and individual rows isolate errors. Notice delivery rechecks
  current owner, recipient and Activation under shared Turn lock. Known inactive/missing endpoint
  requests retire through existing claim/fail fences without targetSession/model; nondelivery
  outcome consumes notice. Live worker lease cannot be stolen.25inactive rows no longer hide26th.
- Independent cbt_selector29handoffPASS2.88s +5maintenancePASS2.47s; no scoped blocker.
  Rootfull1522passed22.55s; Ruff/diffclean,111currency/Dailygolden included. No new SQL, models,
  production data, endpoint or privacy authorization. Gate A release certification remains absent.

### Phases 4–6 review fixes — final verification / STOP owner review

- Final implementation8252738 on develop. Actual commit/file/coauthor index:
  proposals/review-fixes-commit-index.json (31commits since reviewed0be20bb, including previously
  completed UI/provenance). Every repair integrated separately. This final evidence slice changes
  only review records, local probe script and fictional browser captures.
- Full1522passed22.55s; Ruff src/tests/scripts and diffcheckclean. Daily instructions,60case suite,
  deterministic suite and currency checker byte-unchanged versus0be20bb;111currency tests and
  Daily golden/Tool-schema checks included. Source fingerprints current; no release Gate A
  certification. No new model requests; candidates remainPlanned, CBTpersonalinputoff.
- Fresh Unix-socket-only PostgreSQL cluster: all45CI SQL files PASS001–021/assertions; schema21;
  all missing-predecessor gates refuse; forced Activation interleave and30trials/155calls no
  deadlock. Final complete proof+filehashes: proposals/review-fixes-final-sql-chain.json;
  reproducible driver: proposals/probes/review-fixes-final-sql-chain.py. Cluster stopped.
  First evidence driver's redundant final version query used wrong function name after its45SQL/
  officialchecks passed; corrected and reran whole chain in another new cluster. Initial attempt
  retained separately, explicitly DRIVER_ERROR. Final proof matches independently reviewed hashes:
 0179aa3d1bc…,0195e3e6b30…,020e5e6a395…,02112d607bf….018unchanged.
- Each SQL edit independently reviewed before integration, including final concurrent FK deletion
  tests for021; exact hashes and separate probes recorded above. Protected edits:017/019/020/021
  only. No edits to.env/config/dbsingleton/smoke; no push/deploy/Supabase. Schema21 cutover remains
  owner-run under docs/runbooks/mode-schema-21-cutover.md, allfive017→021 in one session.
- Scheduler smokePASS. Frontend ESLint/buildPASS1992modules (existing>500kchunkwarning).
  New preference UI: desktop1440/mobile390 fictional browserPASS defaultoff/keyboardoptin/out,
  failedwrite lock+refresh/focus/nooverflow/runtimeerrors[]. Detector[]; root viewedboth captures;
  fresh independent finish review disposition ship, no materialfixes. Evidence sourcehashes and
  screenshots: .impeccable/review/mode-suggestions/. No production authorization claim.
- Three managed review checkouts archived recoverably; earlier temporary database and preview
  stopped. All independent reviewer clusters stopped. No active model jobs; no Issue09 repository
  threat model/code. Android remains untested.
- Provisional limits for owner review: explicit retained-version policy untilForget/off;7dayactive/
 30daybackup Forget propagation still needs operational verification. Qualified wellbeing/privacy
  gates remain closed. Provider endpoint creation follows atomic logical opening via retry receipt;
  failure notices offer at-most-one attempt, so crash/uncertain provider acceptance may lose notice.
  No claim of exactly-once provider delivery or comprehensive crisis-language detection.
- STOP here for owner review. No new Phase6/Issue09 work.

## Takeover (reviewer as builder) — candidate evals, Issue 09 draft, Gemini blocker — 23 Oct 2026

- Commits: c5d918b Issue 09 threat model draft (docs/security/mcp-a2a-threat-model.md, no code);
  f9c45f4 Coach meaning rubric (improvement_claimed, human_support polarity, contraction expansion);
  4ad0ac9 Recommender/Reflect meaning rubric (no_live_weather, task_limit, stop_acknowledged);
  0371b65 owner Coach hyphen edit. Protected/SQL: none. Daily instructions/Tool schema/60 cases unchanged.
- Rubric changes fix only false negatives on correct Claude replies. Five independent review rounds;
  every adversarial string is a test. Stored replies rescored HEAD vs new: 0 pass->fail.
- Claude CLI (sonnet) runs: v2 invalid (subscription limit, ClaudeCLIError); v3 at faf40be source:
  Coach 45/48, Recommender 41/48, Reflect 56/60 — all failures rubric false negatives.
  v4 at 4ad0ac9: Coach 48/48 PASS, Recommender 48/48 PASS (`*-claude-v4-full.json`).
  Reflect v4 57/60: three rubric false negatives on correct replies (human_support misses
  "connections/relationships with people matter"; reflect-hard-08 phrase ban "you have" hits
  "If you have a concern"). Not fixed: Reflect stays Planned; owner stop.
- Gemini final runs aborted: free tier 20 requests/day (429 RESOURCE_EXHAUSTED) on first case;
  artifacts `*-gemini-v2-final.json` status aborted_provider_incident. Usage file totals now
  22 requests / 17 ok / 30,914 input / 6,053 output tokens. Owner chose to stop: no billing.
  One full suite needs ≥48 requests, so free tier cannot complete any declared run.
- Coach/Recommender remain Planned (no Gemini evidence). Reflect remains Planned regardless.
- Full suite 1649 passed; Ruff clean. STOP: Issue 09 threat model awaits owner + independent
  security review; Gemini evidence needs paid quota.

## Go-live slice — access tiers, trial, guide, privacy notice, Coach live — 23 Oct 2026

- Commits: 1e7b06c full-access allowlist + 30-message trial (`ACCESS_MODE=registered`, alias
  `invite`), `/help`, `count_participant_messages` in all three Stores; b30275b rubric
  (human_support relationship wording, should/must/need-not non-dependence, reflect-hard-08 label
  bans; independent review applied; stored rescore 0 pass->fail / 3 fail->pass); 53a7d17 tiered
  entitlements (Daily+Coach everyone, Reflect/Recommender full access or grant), guard bypass for
  full access (crisis routing still first), Coach consent button, `/api/modes` trial usage +
  dashboard chip; 89d3c0e `/guide/` page + nav/footer/dashboard links; 2081039 privacy notice
  covers bot+dashboard, contact "Getting full access"; 5f4b7a4 onboarding adds 18+ and processor
  acknowledgements (policy 2026-10-23); a882232 Coach live pinned to `google:gemini-3.8-flash`,
  live-Mode evals drop admission guards like candidate runs.
- Protected edits: `src/config.py` (access_mode Literal, trial_message_limit, trial_contact,
  guide_url, coach_trial_enabled). No migration, no `.env`, no push/deploy/Supabase.
- `src/access.py` added to INVALIDATING_INPUT_PATHS. Daily instructions/Tool schema unchanged.
- Tests 1706 passed; Ruff clean; smoke scheduler PASS; deterministic live subsets daily+coach PASS;
  site/web lint+build PASS; guide verified 390/1440 px no horizontal scroll.
- Gemini 3.8 flash (paid): Coach candidate 48/48 (pre-flip) and 48/48 on final code
  (`coach-gemini-3.8-flash-final.json`); Reflect 56/60 (nonmut-02 x2 real: asks consent instead of
  question; nonmut-08, hard-01 rubric false negatives); Recommender 43/48 (all 5: says
  "synthetic/fictional" not required phrase "simulated"); Daily 145/180 FAIL (default not switched).
  Claude Coach v5 47/48 (rubric false negative, fixed in b30275b).
- Provisional decisions: Coach on 3.8 via ModelPolicy primary; trial applies in every access
  mode; full access bypasses Coach/Reflect guards (owner request); new activation policy applies
  to new signups only (acknowledgements immutable per migration 013).
- Open questions: migration 022 for renewed acknowledgement of existing accounts; Recommender
  rubric vs prompt fix; owner approval of privacy notice + Coach notice wording; verify Gemini
  paid-tier no-training terms on production project; products social image text; release-grade
  (clean-tree, baseline-chained) evidence; Render env ACCESS_MODE=registered,
  COACH_TRIAL_ENABLED=true, ALLOWED_TELEGRAM_CHAT_IDS.
- Daily comparison (same suite, 3 reps, paid key): gemini-3.5-flash (current production) 137/180,
  gemini-3.8-flash 145/180; both fail Gate A. 3.8 fails strictly fewer cases (2 unique vs 6
  unique; 15 shared, incl. ga-hard-09/10 safe crisis replies rejected by legacy phrase rubric).
  Recommendation: owner may set Render DEFAULT_MODEL=gemini-3.8-flash as a no-regression switch;
  code default unchanged. Shared Daily failures need rubric-vs-model triage (separate slice).
- Daily on gemini-3.5-flash-lite: 117/180 (hard 17/30, safety 24/42, tool_and_state 109/150,
  no_unnecessary_mutation 156/180); 10 cases fail only on Lite, including real harms: marks an
  ambiguous "the call" done without asking (ga-life-10), applies Later without the canonical
  flow (ga-life-15), claims a Reminder was set with no tool call (ga-task-04). Not suitable for
  Daily. Recommendation: DEFAULT_MODEL=gemini-3.8-flash for every Mode.

## Review findings batch 2 (23 Oct 2026)

- 06ba168 refactor: one handoff recovery path in HandoffController (main.py logic moved; CLI now also rechecks activation).
- 25fd8e2 refactor: one Mode admission check `admit()`; Telegram Turn resolves once (regression test added, fails without fix).
- docs: architecture.md updated (Coach live, tiers, admit, recovery).
- Touched: src/handoffs.py, src/main.py, src/agent/policies.py, src/agent/runtime.py, src/api/modes.py, src/bot/modes.py, src/bot/turns.py, src/coaching.py, src/turns.py. No protected files.
- Evidence: pytest 1714 passed; ruff clean. No billed model runs.
- Open: src/turns.py and Mode modules are Gate A inputs, so earlier Gate A evidence is now stale; re-run needs owner approval (billed lock).
- Not changed: conversations.close_expired keeps entitled()+live check without the entry guard on purpose (a missing consent tap must not close the conversation).

## Owner request 23 Oct 2026: all Modes live, examples, dashboard switch, Coach templates

- 13a1d95 Reflect + Recommender live (full access only, gemini-3.8-flash pin); Mode intros list examples; Coach prompt: example answers + drinking/smoking as habit with see-a-doctor line.
- ad72e6d POST /api/modes/{id}/open, GET /api/coaching/templates (8 templates), I agree tap opens Coach.
- web commit: chips switch on click; CoachTemplates grid.
- Evidence: pytest 1717 passed; ruff clean; deterministic subsets pass for all 4 Modes; web lint/build clean.
- Provisional: Reflect 56/60 and Recommender 43/48 are not passing evidence; live on owner's explicit call. Coach prompt changed, so Coach 48/48 evidence is stale. No billed runs.
- Not changed: CBT personal input stays off (no such feature switched); site copy still says Reflect/Recommender planned.
- claude -p (sonnet, candidate, no API keys) on current code: Recommender 48/48, Reflect 58/60 (1 CLI request failure, 1 human_support rubric miss), Coach 39/48 -> length overflow from example rule -> prompt tightened -> Coach 48/48. Artifacts: .scratch/modular-modes/evals/*-claude-live*.json. Not Gemini evidence.

## Owner request 30 Oct 2026: CBT research Mode, personal input, full access

- Uncommitted. New `src/agent/cbt.py` (id `cbt`, name "CBT (research)"): one situation, one
  question per reply (facts, missing fact, thought, unknowns, possible alternative, optional
  takeaway; at most six), stop/skip/new, no Tools/context/Memory, Daily handoff only on request.
  Question order from `.scratch/mode-expansion-planning/cbt-research-mvp/`; wording provisional.
- Live in catalogue for full-access accounts (`FULL_ACCESS`), `google:gemini-3.8-flash`,
  `reflect_entry_guard`. `reflect_safety_response` now also routes crisis language in `cbt`.
- Owner overrode "CBT personal input stays off" (AGENTS.md updated) and decision 03 (research-only)
  for full-access chats. Decision 15 naming rule ("not CBT until qualified review") overridden too.
- Eval suite `evals/cbt/v1/` (13 cases, mostly Reflect safety/boundary cases adapted, 2 new step
  cases) + deterministic subset. No model run: no evaluated evidence; live on owner's call.
- `src/agent/cbt.py` added to INVALIDATING_INPUT_PATHS; `src/wellbeing.py` changed (Gate A input).
- Not in Mode suggestions, Memory scopes, or migration 021 targets (intentional).
- Open: qualified practitioner review of wording; privacy notice does not mention CBT research;
  site copy unchanged.

## Owner request 30 Oct 2026: channel identities, Phase A (ADR 0004 + migration 022) — STOPPED for owner review

- Plan: ~/.claude/plans/draft-the-refactor-plan-mossy-spark.md (phases A-F; dashboard primary-channel picker
  and dashboard-token second-app Pairing approved by owner).
- Protected files: `migrations/022_channel_identities.sql` (new), `src/schema.py` (21→22). Also
  `.github/workflows/ci.yml` (022 + assert_022 in the SQL chain), `tests/sql/app_schema_version.sql` (expects 22),
  new `tests/sql/assert_022_channel_identities.sql`, `docs/adr/0004-channel-identities.md`, `docs/architecture.md` link.
- 022 adds: `channel_identities` (service_role SELECT only), Telegram mirror trigger, `user_profiles.primary_channel`
  (deferred FK to a linked identity), nullable `telegram_chat_id`, `reminders.delivery_channel/channel_message_ref`
  (+ backfill), `complete_pairing` redefinition, `complete_pairing_v2`, `set_primary_channel`,
  `finish_reminder_delivery_v2` (v1 now routes through it), `channel_update_claims` + claim/finish (Telegram delegates
  to `telegram_update_claims`).
- Two `complete_pairing` decisions change, both only for a profile whose `telegram_chat_id` is NULL: it now links
  Telegram instead of conflicting, and two distinct profiles now conflict explicitly. Behaviour for Telegram-only users is unchanged.
- Evidence (local throwaway PG15, not Supabase): full CI SQL chain of 47 files exits 0 at version 22. assert_022 passes.
  022 re-apply is refused. Backfill is 2/2 for legacy users. pytest 1744 passed; ruff clean. No billed model runs.
- Independent migration review (subagent): 1 blocker (CI chain not updated), now fixed. Should-fixes also fixed:
  - v1 delivery dual-write.
  - Stale Telegram proof is cleared on non-Telegram delivery.
  - Added tests: Telegram v2 accept, retry, v1 path, legacy profile second app, conflict keeps the token, mirror delete, cascade delete.
  - Canonical Telegram ids, a STABLE JSON helper, `search_path=''`, the `updated_at` bump, NULL channel validation.
  - Reviewer's concurrency probes: no deadlocks; same-auth and same-identity races resolve to paired/conflict.
- Provisional: outbox payloads still carry `telegram_chat_id`; the drain will ignore it (Phase D), and 023 drops it.
  The 017 handoff listing still returns `telegram_chat_id`; 023 drops it.
- Open:
  - Gate A evidence is stale, because the hashed inputs include `migrations/*.sql`. A re-run needs owner approval (billed lock).
  - Apply 022 and deploy in one back-to-back step, because the exact-match version gate fails closed.
  - Profiles without Telegram are not production-ready until Phases B-E move the remaining `telegram_chat_id` reads.

## Channel identities, Phase B (Store, three implementations)

- New `src/memory/identities.py` (`LocalIdentityState` + shared 009/022 rules) used by InMemoryStore and FakeStore.
  All three Stores gain: `get_user_by_channel_identity`, `list_channel_identities`, `set_primary_channel`,
  `complete_channel_pairing`, `claim_channel_update` and `finish_channel_update`. `finish_reminder_delivery` also takes
  `channel` / `channel_message_ref`; Supabase now calls `finish_reminder_delivery_v2`.
- Local stores now mirror the SQL:
  - `telegram_chat_id` mirror trigger.
  - Deferred primary-channel key, with rollback on failure.
  - The `complete_pairing` changes from 022.
  - 009 identity-conflict and replay rules (previously they diverged from the SQL).
  - v2 delivery validation runs before any write.
  - Token expiry boundary (`expires_at <= now` is invalid).
- `FakeStore.users` is now keyed by `user_id`, not chat id. The 3 `test_allowlist` assertions became `get_user_by_chat_id(...) is None`, which is not weaker.
- `src/cli.py`: the dev fixture links a `cli` identity through dashboard-token Pairing and `set_primary_channel`. Before this,
  it wrote an unlinked primary, which the new key now rejects.
- `src/evaluation/gate_a.py`: added `src/memory/identities.py`, which is newly reachable.
- Supabase `update_user` maps the deferred-key violation to `ChannelNotLinkedError`.
- Evidence: pytest 1787 passed (43 new in `tests/test_channel_identity_store.py`); ruff clean. No billed runs.
- Independent Store review (subagent): no blockers. Fixed:
  - Should-fixes 1-4 and 6: local Telegram claim/finish parity, finish validation, delivery validation before writes, Supabase FK error mapping.
  - Nits: mirror runs only on change, expiry boundary, dead `forget_user` removed.
  - Requested tests added.
- Deferred to Phase D: scheduler call sites (`src/scheduler/reminders.py:119,306,393,424`) still default to
  `channel="telegram"`, so CLI deliveries record `delivery_channel=telegram`.
- Known/kept: local `validate_identity` rejects any surrounding whitespace, which is stricter than SQL `btrim`.
  Supabase `get_user_by_channel_identity` makes 2 round trips.
- Gate A evidence is still stale (owner approval needed to re-run).

## Channel identities, Phase C (protocol typing, participant lock)

- `ParticipantTurnSerializer` is now keyed by participant: `user:<user_id>`, or `<channel>:<recipient>` while unpaired.
  The update coordinator (`ChannelUpdateCoordinator`, renamed from `TelegramUpdateCoordinator`) resolves the key from
  channel identities. The dashboard Mode switch (`main._open_mode`), handoff recovery and the CLI lock the same key.
  As a result, one participant's Turns serialize across channels. A mutation probe confirmed the new test fails
  when the lock is keyed by chat id.
- The coordinator claims and finishes through `claim_channel_update` / `finish_channel_update`, which delegate to 009 for Telegram, so
  dedup is unchanged.
- `IncomingUpdate` moved to `src/channels/base.py`; added a `Recipient = str | int` alias. Channel-neutral `chat_id`
  annotations are widened (tools, scheduler, turns, handlers, reminder actions, access message).
- Provisional: Telegram values stay int; only annotations widened. Values are compared only within the channel that produced them.
  `recipient_for` stays per adapter; a future adapter can hold the Store and read `list_channel_identities`.
  `decode_update` is not in the `MessageChannel` protocol, because only each channel's own webhook ingress decodes.
- Gate A: added `src/bot/update_claims.py`, which `src/handoffs.py` now reaches.
- Evidence: pytest 1789 passed; ruff clean; `smoke_check.py --scheduler` passes. No billed runs.
- Perf note: each inbound update now does a participant lookup (2 Supabase round trips). An embed or a user-id-only lookup
  is a possible follow-up.

## Channel identities, Phases D+E (channel-neutral delivery; registry not built)

- New `src/channels/delivery.py`: `reachable_here` / `proactive_recipient` hold the one rule that
  proactive messages go only to `primary_channel`. It replaces the copies in `scheduler/reminders.py` and `scheduler/coaching.py`.
- Reminder reconciliation gates on the primary channel (the join now carries `primary_channel` in all 3 Stores), not on
  `telegram_chat_id` being present. Before this, a non-Telegram participant's Reminders were never scheduled.
  Job and outbox `chat_id` is only a hint (`payload.get`), because delivery re-resolves at fire time.
- Delivery proof is recorded against the sending channel (`_delivery_proof`). CLI deliveries now record `delivery_channel=cli`.
- `CommandContext.surface` is now `str`. Tools, Reminder buttons and Coaching commands use `channel.channel_id` for the surface and
  key prefix. A snapshot test confirms Telegram keys are byte-identical (`telegram:<turn>:...`). The `coach:` keys are unchanged.
- **Provisional decision (codebase-design skill, now in AGENTS.md): no `ChannelRegistry`.** Each process runs exactly one channel
  (Telegram in production, CLI locally), so a registry would be a one-adapter, hypothetical seam that fails the
  deletion test. A process whose channel is not the primary never sends; the primary's process delivers. Add the
  registry only when two channels run in one process.
- Kept Telegram-only on purpose: `access.is_full_access_user` (reads the mirrored `telegram_chat_id`), `bot/pairing.py`
  `/start` (Telegram adapter; other adapters call `store.complete_channel_pairing`), `smoke_check.py --channel`,
  and the Activation step "telegram".
- Gate A: added `src/channels/delivery.py`.
- Evidence: pytest 1793 passed; ruff clean. New tests cover primary-only delivery with proof, primary-only
  reconciliation, and the Telegram key snapshot. No billed runs.
