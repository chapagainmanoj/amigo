# Principles, Best-Practices & Anti-Patterns (Amigo)

Single source for code-structure rules. Cite by id (`cosmic-python:AP-DICT-AS-MODEL`); don't
restate. Add an entry when a review finding recurs. Adapted from meaningfy-ws/skillery
`cosmic-python` (Apache 2.0) and fitted to Amigo's AGENTS.md, which wins on conflict.

## Principles

| id | Statement |
|----|-----------|
| `PR-SURVEY-FIRST` | Before a new file/class/function, read siblings in the target package and grep for existing constants, enums, models, Store methods, helpers. Decide reuse / extend / refactor-to-fit first. |
| `PR-SSOT-DRY` | Every fact, constant, mapping or rule has one home; everything else imports or cites it. Same for docs. |
| `PR-DEPENDENCY-INWARD` | Imports follow `ALLOWED` in `tests/test_layering.py`: entrypoints → services → adapters → domain, config readable from adapters and up. Services may import concrete adapters (the Store); domain imports only domain. |
| `PR-DB-IS-AUTHORITY` | Durable state lives in the database via the Store. Schedulers, caches and channel state are rebuildable projections. |
| `PR-MODELS-OVER-DICTS` | A structured payload crossing a function/file boundary is a Pydantic model or frozen dataclass. Raw dicts stay at an adapter's I/O edge. |
| `PR-INJECT-TIME-AND-IO` | Domain receives time, settings values, Store and channels as parameters. Services and entrypoints may call `src.utils.utc_now()`; domain takes a `clock: Clock = default_clock` parameter and never calls `utc_now()` / `datetime.now()` directly. |
| `PR-CONFIG-DECOUPLED` | Settings are read at the edges (entrypoints, composition in `main`/`cli`/`api.dependencies`, adapters) and passed in as values. `LazySettings` keeps tests secret-free; domain never imports `config`. |
| `PR-REUSE-COMPACT` | Prefer the smallest correct, reusable shape. Collapse near-duplicates into one parameterised form; a small enabling refactor is part of the task. |

## Best-practices

| id | Practice |
|----|----------|
| `BP-CONSTANTS-ENUMS` | Symbolic identifiers (statuses, Mode ids, callback prefixes, keys) are constants/enums/`Literal`s in one module, in every layer. |
| `BP-VALIDATE-AT-BOUNDARY` | Validate once at the entrypoint/service entry; rely on typed contracts inside. |
| `BP-DOMAIN-REVEALING-NAMES` | Name modules for the domain thing (`time_resolution`, `conversations`), using `CONTEXT.md` terms. No new `utils.py`/`helpers.py`/`manager.py`. |
| `BP-PROTOCOL-PORTS` | Ports are `typing.Protocol` in an inner layer (`channels/base.py`, `agent/policies.py`); adapters satisfy them structurally. |
| `BP-FAKES-OVER-MOCKS` | Test services with fakes from `tests/fakes.py`; `Mock` only for third-party edges. Extend the fake rather than patching internals. |
| `BP-CONTRACT-TESTS` | A test suite run against both the real adapter and its in-memory twin proves they are substitutable. |
| `BP-FIRST-TESTS` | Tests are Fast, Independent, Repeatable (inject `Clock`, no network, no billed models), Self-validating, Timely. |
| `BP-ERRORS-BESIDE-OWNER` | Exceptions live beside the contract that raises them (`ModeUnavailableError` in `agent/modes.py`, command errors in `commands/base.py`); reuse before minting. |
| `BP-ASYNC-EVERYWHERE` | Amigo is async-first (AGENTS.md). **`async def`** for anything that does or might do I/O, and for every method on an interface others implement or swap: Store, channels, Protocols, policies, entry guards, context providers, Tools, commands, services, even when today's implementation is pure (a later implementation may await). **Sync `def`** only for pure deterministic computation that never sits behind such an interface: parsers, validators, derivations, value-object/dataclass helpers, Pydantic validators, sort keys (`time_resolution`, `activation`, `dashboard_snapshot`, `ModeDefinition` checks). Never wrap pure code in `async` just to match; never do blocking I/O in a sync function. |
| `BP-OWNED-RESULT-TYPES` | Services return Amigo-owned types; framework types (Pydantic AI messages, Telegram updates) don't leak past their adapter/runtime. |
| `BP-LOGS-AT-THE-EDGES` | Logging and metrics in services, adapters and entrypoints; content-free (no participant text). Domain doesn't log; it returns outcomes. |
| `BP-GATE-A-INPUTS` | A module newly reachable from a Turn is added to `INVALIDATING_INPUT_PATHS` in `src/evaluation/gate_a.py`; `tests/test_gate_a_currency.py` is never weakened. |

## Anti-patterns (smell → fix, why)

| id | ❌ Smell | ✅ Fix | Why |
|----|---------|--------|-----|
| `AP-OUTWARD-IMPORT` | Any import `tests/test_layering.py` rejects: domain → anything else, adapter → service/entrypoint, service → entrypoint | Move the shared piece inward or pass it in; never grow `KNOWN_EDGES` silently | Cycles; inner code can't be tested alone |
| `AP-SUPABASE-OUTSIDE-STORE` | Supabase client/query outside `MemoryStore` | Add a Store method (all three impls). Exemption: `src/auth.py` verifies the dashboard JWT with Supabase Auth (no table query); tests override its FastAPI dependency | One place for queries and evidence |
| `AP-STORE-DRIFT` | Store method changed in only one of `MemoryStore` / `InMemoryStore` / `FakeStore` | Change all three in one diff; contract test | Tests pass on a fake that lies |
| `AP-PROTOCOL-DRIFT` | `MessageChannel` changed without every implementation (AGENTS.md list) | Update all; run their tests | Breaks at runtime in the channel nobody tested |
| `AP-AGENT-SIDE-EFFECT` | Store write, send, or schedule from `src/agent/` | Expose as a Tool in `src/tools/` | Agent output must be reviewable before effects |
| `AP-PROVIDER-LEAK` | `telegram`/`discord`/model-SDK import outside its adapter; provider thread ids in app code | Keep in the adapter; pass `ConversationRef` / routed model | Second channel or model becomes a rewrite |
| `AP-IO-IN-DOMAIN` | Network, DB, `config`, or a direct clock call (`utc_now()`, `datetime.now()`) in a domain module | Inject per `PR-INJECT-TIME-AND-IO` | Domain tests become slow and flaky |
| `AP-WALLCLOCK` | `datetime.utcnow()` / naive `datetime.now()` anywhere | `utc_now()` in services/edges; `Clock` param in domain | Naive times; untestable time logic |
| `AP-LOGIC-IN-EDGES` | Business rule in `api/*`, `bot/*` or a channel adapter | Move to a command/service or domain function | Telegram, Discord, CLI and API drift apart |
| `AP-CROSS-MODE-IMPORT` | One Mode module (`agent/coach`, `cbt`, `reflect`, `recommender`) importing another | Share through `agent/modes`, `tools`, or a domain module; route via handoffs | Modes stop being independently entitled and evaluated |
| `AP-MISPLACED-SHARED-INFRA` | Reusable helper buried in one adapter/service and imported sideways | Move to its natural home (`utils`, domain module) | Hidden dependency direction |
| `AP-DICT-AS-MODEL` | Raw dict as a cross-boundary contract | Pydantic model / dataclass | Hidden schema, magic keys |
| `AP-FREESTR-ANYLAYER` | Magic strings (`if mode == "coach"`) in any layer | `BP-CONSTANTS-ENUMS` | Refactor-fragile |
| `AP-DUP-CONST` | Same constants in sibling modules | Lift to one module, import | Copies drift |
| `AP-DUP-VALIDATION` | Same check at many call sites | `BP-VALIDATE-AT-BOUNDARY` | Rules diverge silently |
| `AP-RETRY-LOOP` | Aggressive retry loops around model calls | Retry once then friendly error (AGENTS.md) | Cost and rate-limit blowups |
| `AP-GENERIC-MODULE-NAMES` | New `utils.py`, `helpers.py`, `factory.py`, `manager.py` | `BP-DOMAIN-REVEALING-NAMES` | Must open the file to learn what it is |
| `AP-OVER-FRAGMENTATION` | Many tiny files splintering one concern | Consolidate (`PR-REUSE-COMPACT`) | Navigation tax |
| `AP-BIG-BANG-RELAYOUT` | Renaming packages into `models/adapters/...` folders wholesale | Layers are roles; move one piece at a time | Huge diff, no behaviour gain |
| `AP-UOW-WITHOUT-ADR` | New Unit-of-Work / message-bus abstraction added ad hoc | ADR first; prefer atomic Store ops / outbox | Second transaction model competing with the Store |

## Cross-links

- Module depth, seams, design-it-twice → `codebase-design`.
- Domain vocabulary → `domain-modeling`, `CONTEXT.md`.
- Hard rules (billed models, protected files, migrations) → `AGENTS.md`.
