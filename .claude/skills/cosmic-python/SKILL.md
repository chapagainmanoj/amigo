---
name: cosmic-python
description: Amigo code-structure rules in the Cosmic Python style — which layer (domain, config, adapter, service, entrypoint) code belongs in, allowed import direction (enforced by tests/test_layering.py), Repository/command/outbox mapping, fakes-first testing per layer, and a cited anti-pattern catalogue. Use when placing new modules, reviewing a diff for layering or boundary violations, planning a structural refactor, or when the user mentions cosmic python, clean/hexagonal architecture, ports and adapters, dependency direction, or "where should this go".
---

# Cosmic Python for Amigo

Scope: **code structure inside the Amigo process**: which layer code is in, what it may import,
how it's tested. Not deployment topology. Not module depth or seam placement; that vocabulary
belongs to `codebase-design`, and the two skills are used together.

Authority, highest first:
1. `AGENTS.md`, ADRs in `docs/adr/`.
2. `tests/test_layering.py`: the enforced layer map (`LAYERS`, `ALLOWED`, `KNOWN_EDGES`).
3. [references/principles-and-anti-patterns.md](references/principles-and-anti-patterns.md): rules
   by id. Cite as `cosmic-python:<id>`; never restate. A recurring finding becomes a new entry.
4. [references/amigo-layer-map.md](references/amigo-layer-map.md): prose explanation of 2, plus
   known edges and how to fix them.

## Layers

Layers are **roles, not folders** (`AP-BIG-BANG-RELAYOUT`).

| Layer | Role | Examples |
|---|---|---|
| Domain | Rules, declarations, value/error types. No I/O. | `time_resolution`, `activation`, `agent/modes`, `channels/base`, `commands/base` |
| Config | Settings, model-route parsing, fail-closed validation | `config`, `model_routing`, `runtime_config` |
| Adapter | DB, chat providers, model providers, measurement sinks | `memory/`, `db/`, `channels/*`, `agent/claude_cli_model` |
| Service | Use cases, application commands, Mode runtime | `turns`, `agent/runtime`, `commands/*`, `tools/*`, `scheduler/*` |
| Entrypoint | Parse → call one service → format; composition roots | `main`, `cli`, `api/*`, `bot/*`, `startup` |

```
entrypoint ─▶ service ─▶ adapter ─▶ domain
                 └──────────────────▶ domain
         config is readable from adapter and up; domain never imports it
```

Classify by role, verified by imports: a module that awaits the Store or reads settings is a
service even if it holds "rules" (`access`, `mode_readiness`). Imports under `if TYPE_CHECKING:`
don't count.

`PR-DEPENDENCY-INWARD` states the rule; `AP-OUTWARD-IMPORT` is the smell. Services import the
concrete `MemoryStore` (no Store Protocol); channels and policies are Protocol ports
(`BP-PROTOCOL-PORTS`).

## Book → Amigo

| Book | Amigo | Note |
|---|---|---|
| Repository | `MemoryStore` + `InMemoryStore` + `FakeStore` | `AP-STORE-DRIFT`, `BP-CONTRACT-TESTS` |
| Unit of Work | none; atomic single Store calls (claims, outbox rows) | `AP-UOW-WITHOUT-ADR` |
| Service layer | `SessionTurnOrchestrator`, `ModeRuntime`, `ModeConversationService` | `BP-OWNED-RESULT-TYPES` |
| Commands | `commands/*`: shared by Telegram, Discord, CLI, API | errors/context in `commands/base` |
| Message bus / events | **none**. The durable outbox (`scheduler/outbox`) and handoffs are the nearest analogue: delivery, not in-process dispatch | `PR-DB-IS-AUTHORITY` |
| Read models (CQRS) | `activation`, `dashboard_snapshot` | reads may skip services; writes never skip the Store |

## Workflows

### A. Placing new code

1. `PR-SURVEY-FIRST`.
2. Classify each piece: decision → domain; I/O → adapter; sequencing + failure policy → service;
   parse/format → entrypoint. A function doing two of these is split.
3. Add the module to `LAYERS` in `tests/test_layering.py` (the test fails until you do).
4. Run the one-minute check:
   - Which layer is it in, and do its imports satisfy `ALLOWED`?
   - Who imports it, and is that direction allowed?
   - What is its one reason to change?
   - Which layer's tests cover it (table below)?
   - Is it a duplicate of something that already exists (`AP-DUP-CONST`, `PR-REUSE-COMPACT`)?
5. Name it per `BP-DOMAIN-REVEALING-NAMES`; extend an existing module before adding a file
   (`AP-OVER-FRAGMENTATION`).
6. Reachable from a Turn? → `BP-GATE-A-INPUTS`.

### B. Reviewing a diff

Run `python -m pytest tests/test_layering.py -q`, then check each touched file against:

| Check | ids |
|---|---|
| Imports | `AP-OUTWARD-IMPORT`, `AP-PROVIDER-LEAK`, `AP-CROSS-MODE-IMPORT`, `AP-SUPABASE-OUTSIDE-STORE` |
| Domain purity | `AP-IO-IN-DOMAIN`, `PR-INJECT-TIME-AND-IO`, `PR-CONFIG-DECOUPLED`, `AP-WALLCLOCK` |
| Logic placement | `AP-LOGIC-IN-EDGES`, `AP-AGENT-SIDE-EFFECT`, `BP-LOGS-AT-THE-EDGES` |
| Implementations in sync | `AP-STORE-DRIFT`, `AP-PROTOCOL-DRIFT` |
| Contracts | `PR-MODELS-OVER-DICTS`, `AP-DICT-AS-MODEL`, `AP-FREESTR-ANYLAYER`, `BP-CONSTANTS-ENUMS`, `BP-OWNED-RESULT-TYPES`, `BP-VALIDATE-AT-BOUNDARY`, `AP-DUP-VALIDATION`, `BP-ERRORS-BESIDE-OWNER`, `BP-ASYNC-EVERYWHERE` |
| Duplication / homes | `PR-SSOT-DRY`, `AP-DUP-CONST`, `AP-MISPLACED-SHARED-INFRA` |
| Tests | `BP-FAKES-OVER-MOCKS`, `BP-CONTRACT-TESTS`, `BP-FIRST-TESTS`, `BP-GATE-A-INPUTS` |
| New abstractions | `AP-UOW-WITHOUT-ADR`, `AP-GENERIC-MODULE-NAMES`, `AP-RETRY-LOOP` |

Report as `file:line — cosmic-python:<id> — fix`. Terse.

### C. Refactoring toward the layers

Pick an entry from **Known edges** in the layer map. Move one piece at a time, keep public names
stable, then delete the pair from `KNOWN_EDGES` (`test_known_edges_are_still_real` forces this).
Run tests + `ruff check src tests scripts` after each move. A change of boundary gets an ADR
(next number in `docs/adr/`) and an update to `docs/architecture.md`.

### D. Keeping the map current

Whenever you refactor or add a package, re-read `LAYERS`/`ALLOWED` and ask whether they still
describe the code. Never add to `KNOWN_EDGES` to make a diff pass without recording why in the
review queue (`.scratch/modular-modes/review-queue.md`).

## Testing per layer

| Layer | Test | Doubles |
|---|---|---|
| Domain | Pure unit tests, parametrized branches, injected `Clock` | none |
| Service / command | Through the public call; assert outcomes and Store state | `tests/fakes.py` (`FakeStore`, `FakeChannel`), fake clock |
| Adapter | Contract tests shared by real + in-memory; SQL in `tests/sql/` | `InMemoryStore` passes the same contract |
| Entrypoint | Parsing, status codes, reply shape | wired with fakes |

Tests stay offline: no network and no billed models (AGENTS.md).

## When not to apply

Spikes in `.scratch/`, one-off `scripts/`, eval harnesses. Don't add a layer to a module with one
caller and no I/O; that is shallow-module overhead (`codebase-design`).

## Related

`codebase-design` (depth, seams), `domain-modeling` (`CONTEXT.md` terms), `docs/architecture.md`.
