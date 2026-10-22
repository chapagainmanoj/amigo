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
