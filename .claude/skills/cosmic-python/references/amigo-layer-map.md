# Amigo Layer Map

**Authority:** `tests/test_layering.py` (`LAYERS`, `ALLOWED`, `KNOWN_EDGES`). This page explains it;
if they disagree, the test wins and this page is updated. Classify every new module there
(`test_every_module_has_a_layer` fails otherwise). Classify by **role, verified by imports**, not by
folder: a module that awaits the Store or reads settings is not domain, wherever it lives.

## Allowed imports

| Layer | May import |
|---|---|
| Domain | domain |
| Config | config, domain |
| Adapter | adapter, config, domain |
| Service | service, adapter, config, domain |
| Entrypoint | everything |

Imports under `if TYPE_CHECKING:` are not counted (no runtime dependency). Use them for
annotations only, e.g. `agent/modes.py` naming `ToolContext`; never to hide a real call.

Services import the concrete `MemoryStore` class directly (there is no Store Protocol);
substitutability comes from `InMemoryStore` / `FakeStore` sharing its methods (`AP-STORE-DRIFT`).
Channels and policies are true Protocol ports (`BP-PROTOCOL-PORTS`).

## Roles

| Layer | Modules (prefix covers submodules) |
|---|---|
| Domain | `activation`, `agent.modes`, `agent.prompts`, `agent.safety`, `bot.keyboards`, `channels.base`, `coaching_templates`, `commands.base`, `dashboard_snapshot`, `evaluation.meaning`, `schema`, `time_resolution`, `utils`, `wellbeing`, `workflows` |
| Config | `config`, `model_routing`, `runtime_config` |
| Adapter | `channels.*` (not `base`, `registry`), `db`, `memory` (not `context`, `sessions`), `model_usage`, `observability`, `telemetry`, `agent.claude_cli_model` |
| Service | `access`, `mode_readiness`, `reliability`, `agent.*` (rest, incl. `policies`, `runtime`, `catalogue`, `registry`), `bot.update_claims`, `channels.registry`, `commands.*`, `tools`, `turns`, `conversations`, `handoffs`, `memory.context`, `memory.sessions`, `coaching`, `mode_suggestions`, `memory_service`, `maintenance`, `scheduler`, `evaluation.*` (rest) |
| Entrypoint | `main`, `cli`, `__main__`, `api`, `bot` (rest), `auth`, `startup` |

Why some modules sit outside their folder's layer:
- `access`, `mode_readiness`, `agent.policies`, `reliability`: entitlement/readiness rules that
  await the Store and read settings → services. `access` owns the access-posture rule
  (`admitted`) and the Activation gate (`activation_completed`) for every handler and sender. `mode_safety_response` lives in `mode_readiness` because it
  awaits the `wellbeing_policy` instance held there; `wellbeing` keeps the pure primitives.
- `bot.keyboards`: pure button declarations shared by scheduler and handlers → domain.
- `bot.update_claims`: per-participant Turn serialization used by `main`, `cli`, `handoffs` → service.
- `channels.registry`: chooses the delivery channel by the access rule → service, not adapter.
- `model_routing`: parses and resolves model routes; no SDK calls → config.
- `commands/*` are the book's *commands*; `commands/base.py` holds their context and error types.
- `prompts`, `schema`, `coaching_templates` are declarations (text, constants).
- `scheduler/reminders.py` mixes job registration (entrypoint) with reconciliation (service) in one
  class; filed as service. Split it if it grows.

## Known edges (`KNOWN_EDGES`)

None. The last pair (`runtime_config` → `agent.catalogue`, `evaluation.model_policy`) was fixed by
splitting the startup gate: `runtime_config.validate_settings` checks settings only;
`startup.validate_runtime_configuration` is still the one call `main` and `cli` make, and adds the
per-Mode evaluation evidence (privacy decision 04).

`test_src_never_imports_outside_the_package` also refuses any `src` import of `scripts` or `tests`:
the image ships only `src` and `evals`.

Fixed on 1 Nov 2026 (architecture review): Gate A evidence checker moved into
`src/evaluation/gate_a_evidence.py`; startup gate split; `memory.context`, `memory.sessions`
reclassified as services; `mode_safety_response` reads `ModeDefinition.safety_referral`.

Fixed on 1 Nov 2026: `reliability` reclassified as service; `dashboard_snapshot` takes a `Clock`;
access posture moved from `bot/handlers` to `access.admitted`; seven Activation checks collapsed
into `access.activation_completed`; `DAILY_MODE_ID` in `agent/modes`; `turns` no longer builds a
Pydantic AI type (`ModeRunResult.reply_only`).

Fixed on 31 Oct 2026: `instant` moved to `utils`; `ToolContext` made type-only in `agent/modes`;
`reflect_safety_response` moved to `mode_readiness`; roles of `access`, `mode_readiness`,
`agent.policies`, `bot.keyboards`, `bot.update_claims`, `channels.registry`, `model_routing`
corrected.
