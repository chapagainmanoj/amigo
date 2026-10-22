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
