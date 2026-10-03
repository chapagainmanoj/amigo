# Add a Memory Service Behind the Memory Trust Contract

Status: open
Label: `needs-info`
Severity: `severity:low`
Type: HITL
Owner: unassigned
Phase: 4 of 5 (part 2 of 3)
Blocked by: [../../amigo-complete-product/decisions/26-memory-demand-evidence.md](../../amigo-complete-product/decisions/26-memory-demand-evidence.md),
[../../amigo-complete-product/decisions/30-memory-storage-and-retrieval-technology.md](../../amigo-complete-product/decisions/30-memory-storage-and-retrieval-technology.md)

> Lighter spec. Expand with `to-spec` once the blockers close. The contract itself is already
> decided in [decision 13](../../amigo-complete-product/decisions/13-memory-trust-contract.md).

## Problem Statement

Every Mode sees only Session history and its own Turn Context providers. Nothing carries confirmed
facts, such as preferences, routines, or goals, across Sessions or between Modes. Decision 13 fixes
a strict contract for durable Memory, including participant confirmation, lifecycle and
reconfirmation, pause controls, and the inspector. Decision 26 (demand evidence) and decision 30
(storage technology) haven't closed.

## Solution (direction)

- **One service.** A single Memory service in its own module owns every Memory read and write.
  Modes never touch Memory storage directly.
- **Reading Memory.** It enters a Turn only through a declared Turn Context provider (`memories`).
  A Mode opts in by listing that provider.
- **Proposing Memory.** Modes propose Memory Candidates through a Memory Toolset. Nothing becomes
  Memory without participant confirmation.
- **Contract enforcement.** Decision 13 is enforced in code rather than in prompts:
  - at most three active, relevant Memories per Turn;
  - every retrieved Memory is untrusted data;
  - Memory never authorizes a Tool;
  - every use is recorded;
  - pause, forget, export, and inspection are all supported.
- **Reflect** gets no automatic Memory, as decision 14 requires.

## Key Decisions to Make

- The storage and retrieval technology (decision 30).
- Which Modes opt in first.
- How the "Based on a saved memory" disclosure travels from a Mode's reply to the channel.

## Out of Scope

- Inferred profiles, mood history, or any Memory created without confirmation.

## Comments
