# Run Durable Multi-Step Mode Workflows

Status: open
Label: `needs-triage`
Severity: `severity:low`
Type: HITL
Owner: unassigned
Phase: 5 of 5 (part 1 of 2)
Blocked by: [04-build-coach-mode-with-coaching-program.md](04-build-coach-mode-with-coaching-program.md)

> Lighter spec. Triage using Coach's trial evidence: build this only if the scheduler and outbox
> prove insufficient.

## Problem Statement

A Turn is a single request and reply. Some Mode behaviour spans days and several steps, such as a
Coaching Program's weekly review or a future guided Reflect flow. That behaviour has to survive
restarts, wait on participant replies, and resume exactly once. Issue 04 builds this from the
scheduler, the outbox, and program state. A second long-running Mode would repeat that work by
hand.

## Solution (direction)

- **Definition.** A declared workflow is a sequence of steps, waits, and participant-confirmation
  points, attached to a Mode definition.
- **Execution.** It runs on a durable-execution layer: either Postgres-backed state reusing the
  existing claim and outbox patterns, or a durable-execution integration supported by the model
  framework.
- **Guarantees.** Every step is idempotent, every wait survives restarts, and every side effect
  still goes through Tools and Commands.

## Key Decisions to Make

- Whether to build on Postgres state or adopt an external engine. An external engine is a hosting,
  cost, and operations decision, and it likely needs new infrastructure and secrets.
- How workflow state is exported and deleted under the privacy contract.
- A migration will likely be needed (protected).

## Out of Scope

- Workflows that act without participant confirmation, and cross-participant workflows.

## Comments

### 22 October2026 — Phase6 reuse decision and declared Coach workflow

Backend0be20bb. See provisional proposal
[phase6-08-durable-workflows.md](../proposals/phase6-08-durable-workflows.md). Coach declares v1 steps
and participant confirmation points over existing018/019 Program/Command/outbox state. Owned
workflow inspection omits content/tokens and performs no transitions.16 tests include worker
replacement at enqueue/claim/dispatch/accepted boundaries on both channel paths; uncertain sends
never retry. No external engine or second lifecycle. No trial insufficiency evidence exists.
Declaration describes current code, not persisted per-Program version binding; future v2 needs
explicit binding/migration review before interpreting existing Programs. Issue stays open for
owner review/trial evidence; no generic arbitrary Tool workflow claim.
