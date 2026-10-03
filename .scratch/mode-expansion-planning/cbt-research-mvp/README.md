# Synthetic CBT-informed research MVP — provisional engineering slice

This separate MVP explores **fixed versus bounded adaptive question selection** using fictional
fixtures and a scripted provider. Unlike the earlier menu preview, it has a question-state engine,
per-run limits, two strategy traces, optional answers/takeaway, and focused engineering tests.
It asks guided questions rather than grading predetermined personal interpretations.

Local verification, 2026-10-03: **18 focused tests pass**, Ruff passes, recipe fixed/adaptive
comparison runs, and an interactive comparison start → skip → stop walkthrough clears all state
and exits before a second run. Independent engineering review is pending; these are not clinical
or personal-use validation results.

Build MVP first, then collaborate with a qualified practitioner to revise the method and research
rubric. Practitioner recruitment does not block this synthetic engineering slice. The original
question wording and rules here are provisional, not qualified-reviewed CBT, a clinical protocol,
or evidence of therapeutic usefulness. No treatment or diagnosis is provided.

Run from the repository root:

```bash
.venv/bin/python -B .scratch/mode-expansion-planning/cbt-research-mvp/research_cli.py
```

Default: print fixed/adaptive traces for the fictional meeting case. Use `--case recipe` to inspect
the missing-fact branch. Use `--strategy adaptive --interactive` to consume fictional answers with
`n`, skip with `k`, or stop/exit the run with `q`. Each interactive run first requires `c` to start;
stopping exits the runner, including comparison batches. No personal text/custom case is accepted.
Terminal echo and scrollback are not private: do not paste personal information. The application
does not echo rejected text or store it in state. Run `--strategy fixed` for baseline alone.

Verification:

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider .scratch/mode-expansion-planning/cbt-research-mvp/
.venv/bin/ruff check .scratch/mode-expansion-planning/cbt-research-mvp/
```

## Contract of this engineering slice

- Exactly one allowlisted fictional situation per run. Starting another case creates a fresh run;
  there is no implicit continuation or access to other Mode data.
- Fixed baseline: facts → reported thought → possible alternative → optional takeaway.
- Adaptive: use a missing-fact follow-up after the recipe's consumed fictional fact answer, or an
  uncertainty follow-up after consumed meeting fact/thought answers. Skipped input cannot be used
  as evidence. Adaptation is scripted fixture branching, **not an LLM or demonstrated expert
  reasoning**; no new questions are generated. A possible alternative is not a prescribed truth.
- **Provisional engineering budget:** at most four question selections and four questions per run;
  zero retries; one displayed question at a time. These numbers are not an approved founder
  personal-use protocol. Skip advances without adding an answer. No-takeaway completion is valid.
- Stop ends the run and clears selected fixture/question/answer metadata immediately. Failed
  selection terminates without exposing provider exception content; no automatic restart.
- All answers come from fixed synthetic fixtures. No personal free-text field, saved transcript,
  data files, model/API/network, secrets, production imports/registry, participant lookup,
  Task/Reminder/Memory Tools, Daily handoff, proactive messaging, or outcome score.
- Stdlib runtime only; pytest/pytest-asyncio and Ruff are existing development dependencies.
  `-B` avoids bytecode writes; pytest's cache provider is disabled in the documented command.
- Stdout intentionally shows synthetic cases/questions/answers for inspection; that is not a
  content-free logging design suitable for later personal input. No persistence is configured,
  but terminals may independently retain displayed fiction in scrollback.

## Gates to real-model and personal use

### Offline typed-selector preparation — 2026-10-03

`selector_adapter.py` prepares a small typed boundary for later evaluation, but includes **no
live provider, network client, API-key handling, or CLI live-mode flag**. The CLI still uses its
original scripted provider. Tests inject mock async transports only. Do not pass a live transport
without separate external-processing/spend approval and independent privacy/safety verification.

- Input is a typed request assembled from an allowlisted fixture, consumed fictional answers,
  previously asked IDs, deterministic state-eligible IDs, and remaining request count. No
  skipped answer or arbitrary caller text enters that request.
- Response must be exactly `{"question_id": "<eligible-id>"}`. Missing output, prose, extra
  fields, invalid IDs, repeated or out-of-state patterns are refused. Questions still render from
  local fixed wording; the adapter cannot generate guidance or change the question contract.
- The adapter additionally has a lifetime four-dispatch cap (one instance per run), counting
  errors/timeouts/invalid output. Zero retries; no fallback. Its positive timeout, at most one
  second, is an **offline mock engineering setting**, not an approved live-provider budget.
- Model-independent `stop()` prevents new dispatches, cancels an in-flight mock transport, and
  discards its output. Engine `stop` continues to clear run state without contacting a provider.
  A future live runner must coordinate these two controls; no existing CLI needs that wiring.
- Safe results contain only an allowed ID or fixed status. Errors expose neither raw transport
  output nor exception text; the adapter has no logger, trace exporter, or persistence writer.
  These mock checks do not establish a real SDK/provider's logging or retention behavior.

Verification: **37 focused tests pass** (original 18 unchanged plus 19 adapter cases), Ruff passes.
Coverage includes typed/eligible output, exact consumed-fiction payload, missing/extra/free-form
responses, state refusal, skip behavior, timeout/error handling, no retries/output/log content,
stop before and during mock dispatch, and budget exhaustion. No actual model/API request occurred.
The offline extension is ready for separate independent review; this is not live or clinical
validation.

### Remaining external-processing gates

The founder selected one everyday situation, guided optional questions, immediate stop, and no
saved personal transcripts for the intended later version. This MVP does not enable that version.

Before a real-model comparison: approve provider processing/retention, exact permitted question
patterns and adaptation policy, limits, content-free traces/error handling, and adversarial safety
fixtures. Replace the scripted provider only by explicit reviewed change—not an API-key flag.
Before personal input: prove trusted founder-only access, no raw content retention/logging, stop
and kill-switch behavior, model-independent limitation/referral fallback and verified resources,
and approve the personal-data/provider/safety protocol. Other participants and production rollout
remain excluded. No claim of expert validation is permissible until the qualified practitioner
reviews the exact method and claims.

Focused tests verify software boundaries for synthetic fixtures only; they do not certify clinical
safety, actual crisis handling, provider privacy, efficacy, or release readiness. No crisis
classification is implemented because personal input is excluded. Source: [current research
plan](../cbt-research-plan.md), [open protocol](../decisions/05-cbt-research-protocol.md).
