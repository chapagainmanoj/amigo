# Triage labels

## Workflow state

| Canonical role | Local label | Meaning |
|---|---|---|
| `needs-triage` | `needs-triage` | Maintainer evaluation required |
| `needs-info` | `needs-info` | Waiting for reporter information |
| `ready-for-agent` | `ready-for-agent` | Fully specified and AFK-ready |
| `ready-for-human` | `ready-for-human` | Human interaction or implementation required |
| `wontfix` | `wontfix` | Will not be actioned |

## Severity

| Label | Meaning |
|---|---|
| `severity:critical` | Launch-blocking security, privacy, safety, or fundamental product risk |
| `severity:high` | Required before the applicable release gate |
| `severity:medium` | Important but may be deferred with an explicit decision |
| `severity:low` | Polish or optimization with limited launch risk |

Workflow state and severity are independent. Every implementation issue should contain one
workflow label and one severity label.

## Wayfinder labels

| Label | Meaning |
|---|---|
| `wayfinder:map` | Canonical map for one destination |
| `wayfinder:research` | AFK investigation that resolves a factual uncertainty |
| `wayfinder:prototype` | HITL artifact used to decide behavior or presentation |
| `wayfinder:grilling` | HITL conversation that resolves a product or architecture decision |
| `wayfinder:task` | Work required to unblock a decision |

Wayfinder type labels describe decision work. They do not replace workflow-state or severity
metadata.
