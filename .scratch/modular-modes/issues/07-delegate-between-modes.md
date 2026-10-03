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
