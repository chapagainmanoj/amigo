# Amigo continuation handoff

## Read fully, absorb, then delete this file

The user explicitly requested this temporary handoff in the project root. Read this document
through EOF, inspect the applicable instructions and referenced current artifacts, and reconcile
them with the actual Git state before acting. After the context is fully read and understood,
preserve any necessary unresolved status in the existing trackers and **delete only this file,
`/Users/mano/Workspace/amigo/HANDOFF.md`, using `apply_patch`**. The user has authorized that
cleanup. Do not delete it before completing the read, or delete other project documentation.
If you cannot absorb the context yet, leave the file in place and explain why.

## Mission and working style

Continue modular Mode development and the small CBT-informed research MVP. The user explicitly
asked the primary agent to act as **orchestrator and mediator**, delegate work to subagents, keep
safe work moving in parallel, review results, and bring them specific decisions/approval requests.
Do not describe an agent as making progress merely because its status says running; require
concrete evidence, surface blockers promptly, and restart stalled agents when appropriate.

Read `/Users/mano/Workspace/amigo/AGENTS.md` first. Preserve dirty work and concurrent human
commits. Use `apply_patch`; no destructive Git, production deployment, commit, or push is authorized.
Protected config, Supabase singleton, smoke check, secrets, and migrations still require human
review. Mirror Store API changes across MemoryStore, InMemoryStore, and FakeStore. Keep side
effects outside `src/agent/`, DB access inside the Store, and Daily instructions/schema unchanged.

## Git and agent snapshot

Last observed HEAD: `571947fe75abc608319d2bd5bab364e6c34a6824` (`Lets continue`), author Manoj.
The human committed much of this session's completed work while agents were active. Do not assume
it is all uncommitted or undo that commit. Run `git status --short` and inspect the actual diff.

All three task agents are frozen/completed for this handoff; no implementation should continue
silently. Agent IDs may not survive a fresh chat; spawn replacement agents if needed:

- `plan_reflect`: implemented the current Store-only slice, not independently reviewed yet.
- `fix_modular_review`: adopted migrations; later began the unfinished live Gemini selector.
- `review_mode_phase2`: independent migration/CBT offline reviewer; Store review **not started**.

Observed dirty/untracked work to preserve:

- `src/memory/modes.py` (new), `src/memory/store.py`, `src/memory/memory_store.py`, `tests/fakes.py`,
  `tests/test_mode_store_contracts.py` (new): Store slice described below.
- `.scratch/mode-expansion-planning/cbt-research-mvp/gemini_selector.py` (new): unfinished.
- `.scratch/modular-modes/proposals/issue03-application-plan.md` (new): unreviewed readiness draft.
- `.scratch/modular-modes/proposals/adopted-016-independent-verification.md` (new): completed evidence.
- Approval/progress notes in CBT protocol, Issue 03, and proposal review records.

## Completed and verified: migration adoption

The user explicitly approved migrations **015/016**. They are adopted in the repository and the
application expects schema **16**. This is **not** production deployment. Daily is still the only
live production Mode; Coach, Reflect, and Recommender remain planned; CBT is not registered.

Read the evidence, rather than reusing historical/lost proposal hashes:

- `.scratch/modular-modes/proposals/adopted-016-independent-verification.md`
- `.scratch/modular-modes/proposals/015-reconstruction-review.md`
- `.scratch/modular-modes/proposals/016-review.md`

Exact reviewed SQL/assertion bytes were copied to migrations/tests. CI, startup gate, schema
assertions, predecessor-refusal guards, README and relevant docs were updated. Independent fresh
PostgreSQL verification applied all 35 CI SQL files through 016; ledger/code agreement, missing
predecessor refusal, and Activation forced interleave plus 30 trials/155 calls passed. Independent
concurrency checks proved grant cap, one confirmation, expiry after lock waits, revocation, and
015's crossed-pairing deadlock fix. A last 016 profile-FK-wait expiry race was fixed and retested.

Before the Store slice: 568 backend tests, Ruff, Gate A contract validation (60 cases × 3), Daily
deterministic evaluation, and whitespace checks passed. No real Supabase/staging proof is claimed.

Temporary PostgreSQL cluster may still be running at `/tmp/amigo-mode016.pFi5g5`, port 55476.
Fresh adopted fixture DB is `amigo_adopted016_review_e5232f81`. Validate these targets before use;
never default to production, reset existing fixtures, or delete broad temporary paths. Cleanup
has not been performed. Completed reviewer process handles are no longer active.

## In progress: Issue 03 Store contracts

Read `.scratch/modular-modes/issues/03-switch-modes-with-confirmed-handoffs.md` and the adopted
`migrations/016_session_modes_grants_handoffs.sql` in full. This issue remains **open**.

The frozen Store slice adds seven async APIs across all three implementations: active Mode
get/set, grant/revoke/get-active grant, create/resolve handoff. New typed DTOs and a shared locked
local-state mirror live in `src/memory/modes.py`. Participant-facing commands, routing policies,
handoff Tools/callbacks, and operator grant script are **not wired**.

Implementer reports 67 focused no-network contract tests and focused Ruff passed. Its original
full-suite session `99854` could not be polled by root (unknown process ID); do not invent a result.
Root reran the full suite during handoff and found a fingerprint regression; see the final
verification note below. Tests against the
production adapter currently use an RPC double, not actual SQL Store execution. Independent
Store review has not started: prioritize SQL/DTO parity, trusted grant flags, owner-filtered reads,
expiry, cap, atomic single-use confirmation, and payload returned only on confirmation. Review
actual changes, fix findings, rerun all tests, and record the result before building on this slice.

Read `.scratch/modular-modes/proposals/issue03-application-plan.md` as a **proposal**, not approved
implementation or reviewed fact. It proposes commands/routing first and identifies a possible
handoff crash-recovery gap: 016 commits confirmation without a durable target-execution claim,
so a crash may lose the carried request; re-running a model may duplicate committed Tools. Verify
this finding before designing a fix. Do not promise reliable exactly-once execution or silently
create migration 017. Any additional schema proposal still needs explicit human approval.

Session history in `src/turns.py` is currently unfiltered across Modes. Sensitive Mode release
needs isolation and privacy controls; the separate CBT harness must never use that transcript path.

## CBT research: user decisions and completed MVP

Critical correction: the user wants **a small research MVP first, then a qualified practitioner,
then further research together**. They are not a CBT expert and are still looking for a practitioner.
Do not block engineering on recruitment or imply any expert review has happened.

Selected boundaries: separate founder-only research harness, CBT-informed thought examination,
one everyday situation per run, one optional question at a time, immediate stop, optional takeaway,
no saved personal inputs/replies/summaries/content logs. Fixed sequencing is a comparison baseline,
not the final design; bounded adaptation is the research interest. No therapy, diagnosis, clinical
scores, treatment plans, efficacy/equivalence claims, commercial rollout, other participants,
other-Mode history, or side-effect Tools. **Personal input is not enabled/approved yet.**

Read existing artifacts rather than duplicating their plans:

- `.scratch/mode-expansion-planning/cbt-research-plan.md`
- `.scratch/mode-expansion-planning/decisions/05-cbt-research-protocol.md`
- `.scratch/mode-expansion-planning/cbt-expert-brief.md`
- `.scratch/mode-expansion-planning/cbt-real-model-next.md`
- `.scratch/mode-expansion-planning/cbt-research-mvp/README.md`

The synthetic MVP and offline selector are implemented and independently reviewed: **37 tests
and Ruff passed** before the unfinished Gemini file was added. Fixed/adaptive fictional branching,
start/skip/stop, budgets, strict eligible question IDs, and generic errors are verified only for
the scripted/mock scope. Coordinated engine/adapter stop is not wired for a live runner yet.
The older `cbt-research-prototype/` is a fixed fictional menu preview, not the research MVP.

Scripted demo (no network):

```bash
.venv/bin/python -B .scratch/mode-expansion-planning/cbt-research-mvp/research_cli.py
```

## Explicit live-batch approval, unfinished implementation

The user approved external processing/spend for the existing project Gemini account, **at most
8 total requests, zero retries, fictional fixtures only, no personal input, no saved model
transcripts**, with model/account-processing checks before execution. Requests actually made:
**0 of 8**. Track failed requests too; do not reset this authorization into repeated batches.

The user reported **free account or settings unknown**. Treat processing as unpaid with unknown
optional logging/sharing; Google may use input/output for improvement and human review. No
provider-side zero-retention claim and no account-setting changes are authorized. Original,
non-sensitive fictional material only. An API key cannot prove billing/logging/account identity.
Root communicated this caveat; approval and answer are recorded in the protocol decision file.

Primary sources checked during this session:

- https://ai.google.dev/gemini-api/terms
- https://ai.google.dev/gemini-api/docs/logs-policy
- https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash

`src/config.py` default is `gemini-3.5-flash`; do not modify defaults. No credentials were read or
calls made while preparing the new file. Use only the existing authorized account credential,
never print a key, modify `.env`, or persist provider bodies. Do not use production Turn/Gate A
evidence paths: they persist transcripts/traces/errors. No current ModelProvider/GeminiProvider
classes exist; the project migrated to Pydantic AI, but this harness stays separate.

`gemini_selector.py` is **incomplete, untested, and not linted/executed**. Known pending work:

1. Resolve `genai.Client` versus the asynchronous `.aio` interface expected by the selector.
2. Replace awkward metric-status typing with a named alias; inspect the whole file for defects.
3. Build an explicit-opt-in runner with safe credential loading, shared 8-request batch cap,
   at most 4 requests per run, one SDK attempt/no retries, timeout and output-token bounds,
   no Tools/grounding, strict eligible-ID output, metadata-only display, and coordinated stop.
4. Add mock SDK/transport tests for counts, invalid/extra/repeated/out-of-state output, error/key
   privacy, cancellation, and request settings. Finish README/provider-assumption documentation.
5. Obtain independent review before actual API calls. Execution may require a separate tool-level
   network approval; surface it promptly, never treat the human batch approval as a sandbox bypass.
6. Run only the authorized bounded batch, record content-free results and actual request count,
   and report engineering findings—not CBT faithfulness or clinical usefulness.

## Immediate continuation order

1. Read/absorb this handoff and AGENTS; inspect HEAD/diff, preserve work, then delete this file.
2. Repair the Gate A invalidating-input closure regression described below; delegate independent
   Store review and the Gemini completion/mock-test slice in parallel.
3. Gate integration on review results. Keep the existing approvals and exclusions exact.
4. Continue Issue 03 commands/session routing after Store PASS; review the crash-recovery finding
   before confirmed target execution. Keep planned production Modes disabled.
5. Keep trackers/docs current; ask the user only for concrete additional choices or authority.

Reflect and Recommender plans remain in `.scratch/mode-expansion-planning/`. Laundry is the first
internal Recommender scenario, with simulated weather; commercial demand/domain/source approval
remains unresolved. Read its existing plan/decisions instead of inventing a new domain. Nothing
about this handoff approves shipping Reflect or CBT personal use.

## Suggested skills

- `review`: independent Standards and Spec review of the Store slice against Issue 03; use a
  verified baseline/diff and read its SKILL.md fully before applying it.
- `tdd`: remaining implementation and regressions, if using test-first development.
- `grill-with-docs`: only for unresolved design decisions; record resolutions in the tracker.
- `handoff`: refresh a continuation handoff if needed; follow explicit user destination/cleanup.

Use the local `.agents/skills/` catalog and read applicable instructions. Do not infer protected
file approvals from a skill. Do not reopen already resolved decisions as repetitive yes/no loops.

## Final verification at handoff

Root's full backend rerun completed: **634 passed, 1 failed** in 14.04 seconds. The failure is
`tests/test_gate_a_currency.py::test_no_reachable_module_escapes_the_invalidating_fingerprint`:
the new reachable `src/memory/modes.py` is missing from `INVALIDATING_INPUT_PATHS`. Update the
canonical invalidation contract appropriately and rerun the test/full suite; **do not weaken the
closure assertion or pretend old Gate A evidence still certifies changed inputs**. The canonical
list is in `src/evaluation/gate_a.py`. This is a confirmed defect discovered after the implementer's
67-test focused PASS. The Store slice still needs independent review.

Root session `66335` is finished; original implementer handle `99854` was unavailable to root.
Root whitespace check passed. Gemini selector remains untested; the prior 37-test PASS applies
to the offline MVP before that addition, not the unfinished live adapter. No production actions
or model API calls were taken. All subagents are frozen/completed.
