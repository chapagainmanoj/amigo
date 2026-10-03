# Integrate External Agents and Tools over MCP and A2A

Status: open
Label: `needs-triage`
Severity: `severity:low`
Type: HITL
Owner: unassigned
Phase: 5 of 5 (part 2 of 2)
Blocked by: [07-delegate-between-modes.md](07-delegate-between-modes.md)

> Lighter spec. Needs a dedicated threat model and an independent security review before any
> build. The founder can't approve that review alone.

## Problem Statement

Every Mode and Tool is built inside the repository. The founder wants external agents and
third-party Tools to plug in without changes to the core. Examples are a specialist coaching agent
from another vendor, or a calendar Tool exposed over MCP. Nothing today can consume them, and
nothing constrains what they could do with participant data.

## Solution (direction)

- **External Tools.** A Mode may declare an MCP-backed Toolset. The runtime wraps it with an
  allowlist of Tool names, fixed schemas pinned by hash (like Gate A's Tool-schema hash), timeouts,
  and a content policy. Its results are untrusted data.
- **External agents.** An external agent can be registered as a Mode, or as a read-only delegate
  under issue 07's rules, through A2A. It gets the Safety Core composition, entitlement, the Turn
  Record, and per-Mode evaluation like any internal Mode.
- **Data minimization.** Only the fields a declared contract needs leave Amigo. Participant
  identity never does.
- **Outbound.** Optionally, Amigo's own read-only Tools could be exposed over MCP to the
  participant's own clients, with per-participant OAuth. That is a separate decision.

## Key Decisions to Make

- The data-processing and privacy terms for each third party. This needs a privacy-policy update.
- Authentication and secret storage for external endpoints. This touches `src/config.py`
  (protected).
- Whether an external agent's model and prompt can be evaluated under decision 09 at all. If they
  can't, it can't be a live Mode.

## Out of Scope

- Letting an external agent call Amigo's write Tools directly.
- Marketplace or discovery features.

## Comments
