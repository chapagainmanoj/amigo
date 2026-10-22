# Amigo handoff — 22 October 2026

## Start here

Workspace: `/Users/mano/Workspace/amigo`. Branch: `develop`.
Latest committed HEAD: `faf40be` (implementation ends at `8252738`; final commit adds evidence).
Tree was clean before creating this requested, uncommitted handoff.

**STOP for owner review.** The latest owner instruction supersedes the older plan's automatic
continuation: finish Phases 4–6 review fixes, then stop. Those fixes are complete. Creating this
handoff does not authorize more Phase 6 work, model runs, or Issue 09 work.

Read before acting:

1. `/Users/mano/.claude/plans/give-me-a-plan-wild-unicorn.md` fully, especially the final
   “Review findings, Phases 4–5”, “Addendum: Phase 6”, and both “Owner decisions” blocks.
2. `AGENTS.md` — canonical repository instructions; this file is session context only.
3. `.scratch/modular-modes/review-queue.md` — “Phases 4–6 review fixes” through final STOP.
4. `docs/adr/0003-mode-topics.md` — Accepted; spike passed Desktop/iOS, Android untested.
5. `git status` and `git log --oneline -5`; account for any changes since this handoff.

The original uppercase `HANDOFF.md` was absorbed/deleted during Phase 0. This new lowercase
`handoff.md` was explicitly requested by the owner; do not repeat the old housekeeping deletion.

## Completed work and evidence

All requested findings 1–5 and 7–20, including the earlier working-tree finding 6, are addressed.
The three owner decisions are implemented: proactive-only budget, explicit
`progress_logged_today` cancellation, and default-off participant Mode suggestions with dashboard
opt-in. Memory off forgets saved records and frees its trial slot. Details belong in the review
queue rather than being duplicated here.

Key references:

- `.scratch/modular-modes/proposals/review-fixes-commit-index.json` — actual commits, files,
  required coauthor footers and final protected SQL hashes since reviewed `0be20bb`.
- `.scratch/modular-modes/proposals/review-fixes-final-sql-chain.json` — complete passing proof.
- `.scratch/modular-modes/proposals/probes/review-fixes-final-sql-chain.py` — reproducible local
  PostgreSQL driver; creates/stops a fresh Unix-socket-only cluster, never Supabase.
- `.scratch/modular-modes/proposals/suggestion-opening-receipt.md` — atomic logical opening,
  provider retry fencing, and concurrency limitations.
- `.scratch/modular-modes/proposals/memory-retention-policy.md` — documented retention option,
  pending owner review; operational backup deletion remains unverified.
- `.impeccable/review/mode-suggestions/` — fictional desktop/mobile captures, source hashes,
  passing browser checks and independent UI disposition `ship`.
- `docs/runbooks/mode-schema-21-cutover.md` — owner-run cutover only; all five 017→021 in one
  session, with preflights and immediate matching deployment.

Final verification at implementation `8252738`:

- Full suite: **1,522 passed in 22.55s**; Ruff `src tests scripts` and diff check clean.
- 111 Gate A currency checks plus Daily golden/Tool-schema checks included. Daily instructions,
  approved 60-case suite, deterministic suite and currency checker unchanged versus `0be20bb`.
- Fresh complete 45-file CI SQL chain passed through schema 21; predecessor guards passed;
  forced Activation lock interleave and 30 trials/155 calls found no deadlock.
- Each SQL edit independently reviewed, including final concurrent Session-deletion probes.
  Changed migrations: 017, 019, 020, 021. Migration 018 unchanged during repairs.
- Scheduler smoke, frontend ESLint/build passed. Existing build warning: bundle >500 kB.
- Initial evidence-driver attempt had a wrong final version-function name after its chain and
  official probes passed. It is preserved as `DRIVER_ERROR`; corrected fresh rerun fully passed.

These are engineering checks, **not release Gate A/model certification**.

## Important state and limits

- Coach, Reflect and Recommender remain **Planned**. No new model requests during repair work.
  Historical full Claude results: Coach 40/48, Recommender 28/48, Reflect 37/60. Do not rescore
  old artifacts or represent partial/cancelled Ollama/Gemini runs as passing evidence.
- `.scratch/gemini-usage.jsonl`: 16 requests; 27,572 known input tokens, 5,644 known output;
  15 successful/1 error, one unknown-usage request. Fresh required Gemini suites must pass before
  any new Mode goes live; do not launch batches merely because this handoff was read.
- Reflect's deterministic safety path is wired, but bounded English routing is not comprehensive
  detection or clinical review. Qualified wellbeing/privacy prerequisites remain closed.
- Memory version history remains visible until Forget/off under the documented policy. Forget
  removes active plaintext immediately; seven-day active/30-day backup propagation still needs
  operational verification. No changed published privacy promise or live admission.
- Suggestion confirmation and canonical Session/selector opening are one DB transaction; provider
  endpoint creation follows through a fenced retry receipt. Failure notices allow at most one send
  attempt: crash/uncertain acceptance can lose a notice. No exactly-once provider delivery claim.
- Production handoff maintenance also recovers persisted failure notices, rechecks Activation under
  the shared Turn lock, and retires unavailable owners without blocking the next queue page.
- Three managed review worktrees archived recoverably in this chat's artifacts. Review agents,
  model jobs, temporary PostgreSQL clusters and fictional preview stopped; start fresh reviewers
  if needed. Do not assume old `/tmp` driver paths or process/session IDs are usable.
- No push, deploy, Supabase apply, `.env` edit, or Issue 09 repository threat model/code.

## Next agent

Wait for owner review/steering; do not infer approval from this handoff. If given findings, make
one commit per fix on `develop`, append concrete evidence to the review queue, and independently
review every SQL change. Preserve the exact coauthor footer from the plan.

Keep all three Stores aligned; keep Telegram implementation details in its adapter; keep Daily
instructions/Tool schema unchanged; update the source fingerprint closure for reachable modules.
Never push, deploy, touch `.env`, or apply Supabase migrations. CBT personal input stays off;
real participants never pinned to Claude. Development iteration uses subscription `claude -p`
without `ANTHROPIC_API_KEY`, Ollama backup, Gemini only authorized final evals with usage logging.

Report extremely concisely, concrete evidence only. No Issue 09 work without new owner direction.

## Suggested skills

- `review`: independent Standards/Spec review of owner-identified changes or migrations.
- `diagnose`: reproducible bug investigation when a new failure is reported.
- `impeccable`: scoped dashboard changes and bounded visual/accessibility verification.
- `handoff`: refresh this context when transferring the next session; honor the owner's requested
  project-root location over the skill's default temporary-directory location.

## Takeover update — 23 October 2026 (reviewer as builder) — STOP

HEAD `4ad0ac9` (+ owner edits uncommitted: AGENTS.md co-author line removed, scripts/dev_tunnel.sh).

- `c5d918b` Issue 09 MCP/A2A threat model draft (no code). **STOP** for owner + independent
  security review before any Issue 09 build.
- `f9c45f4`, `4ad0ac9` meaning-rubric fixes (Coach / Recommender / Reflect false negatives); five
  independent review rounds; adversarial strings are tests. `0371b65` owner Coach hyphen edit.
- Claude CLI v4 at `4ad0ac9`: Coach 48/48, Recommender 48/48 PASS. Reflect v4 57/60 (3 rubric false
  negatives recorded in review queue; unfixed, Reflect stays Planned).
- Gemini final runs aborted: free tier 20 requests/day; one suite needs ≥48. Owner chose stop,
  no billing. Coach/Recommender stay **Planned**; Reflect stays Planned regardless.
- Gemini usage: 22 requests, 17 ok, 30,914 in / 6,053 out tokens.
- Next when owner enables paid Gemini: `scripts/run_gate_a_eval.py --mode <coach|recommender>
  --candidate --model google:gemini-3.5-flash --repetitions 3 --output
  .scratch/modular-modes/evals/<mode>-gemini-v3-final.json`; promote to `status="live"` only on
  pass (no fallback model declared, so no fallback evidence needed); grant-only entitlement.
- Full suite 1649 passed; Ruff clean. No push/deploy/Supabase/.env.
