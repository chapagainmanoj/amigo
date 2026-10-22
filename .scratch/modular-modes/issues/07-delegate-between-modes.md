# Delegate a Bounded Question from One Mode to Another

Status: open
Label: `needs-triage`
Severity: `severity:low`
Type: HITL
Owner: unassigned
Phase: 4 of 5 (part 3 of 3)
Blocked by: [04-build-coach-mode-with-coaching-program.md](04-build-coach-mode-with-coaching-program.md)

> Lighter spec. Triage first: confirm there's a real need that a confirmed handoff (issue 03)
> doesn't already cover.

## Problem Statement

A handoff switches the participant into another Mode. Sometimes a Mode needs an answer from
another Mode's capability without switching. For example, Coach might need to ask "what is on
today?" before suggesting a check-in time. Today the only way is to give Coach Daily's Turn Context
provider directly.

## Solution (direction)

A Mode may declare **delegates**, which are other Modes it may consult through read-only
delegation. The runtime runs the delegate as a sub-agent:
- with the delegate's own instructions and the Safety Core;
- with a read-only subset of its Toolsets;
- inside the same participant's Tool Context, with a strict per-Turn budget.

The delegate returns plain text to the calling Mode as untrusted data. Delegation can never cause
a side effect. Anything that writes still goes through a confirmed handoff.

## Key Decisions to Make

- Whether shared Turn Context providers are enough. If they are, close this as Do Not Build.
- **Tool marking.** How Tools are marked read-only. A declared property on the Tool, enforced by
  the runtime.
- **Budgets.** Nesting depth (proposed: 1) and token budgets, and how they appear in the Turn
  Record.

## Out of Scope

- Delegation that writes, delegation to external agents (issue 09), and multi-step workflows
  (issue 08).

## Comments

## 22 October 2026 — Phase 6 triage, provisional — owner review

Recommended outcome: **Do Not Build internal Mode delegation**. No runtime delegation,
read-only Tool marking, nested model calls, or new cross-Mode data permission added.
Issue remains open for owner review of this triage record; this is not an automatic-routing
approval or a claim that the specialized Modes passed their external demand gates.

Concrete coverage:

- The issue's “what is on today?” example is an owned Store read already expressible by a
  declared `todays_tasks` Turn Context provider (`src/agent/context.py`). Coach currently declares
  only its Coaching Program provider; giving Coach Task context still needs explicit minimal
  data approval. The provider's existence does not grant that access.
- An ordinary Task/Reminder request from Coach already uses `propose_handoff` → visible
  participant confirmation → Daily's own Session/Tools/Commands. Undeclared targets and
  cross-owner callbacks deny; decline/expiry/withdrawal run no target Turn.
- Mode-scoped transcripts and summaries remain isolated; confirmed payload alone crosses.
  Durable replay recovers the exact target plan without duplicating Tasks/Reminders.

Verification: `.venv/bin/python -m pytest tests/test_mode_routing.py
 tests/test_mode_candidates.py tests/test_coaching_application.py -q` → **89 passed, 1.99s**.
This covers both threaded/command channels, Mode Tool boundaries, undeclared handoff targets,
confirmation racing/double taps, cross-owner/withdrawal denials, history/summary isolation,
Task/Reminder crash replay, and actual Coach Tool/controller boundaries. Fictional inputs only.

Missing evidence: no reproducible participant job requiring another Mode's independent reasoning
without a visible switch; no demonstrated failure of a minimal approved context provider or
confirmed handoff; no approved additional data-sharing scope; no measured benefit against added
latency/token/failure/privacy cost. Decisions14/23/28 preserve explicit selection and deny silent
cross-Mode data flow; decisions26/30 concern Memory demand/technology and provide no delegation
approval. Reopen only with these artifacts and the bounded controls listed in the proposal.

Detailed record: [phase6-07-delegation-triage.md](../proposals/phase6-07-delegation-triage.md).
