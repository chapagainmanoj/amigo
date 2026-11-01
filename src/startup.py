"""Fail-closed application startup: the configuration gate, then side-effect ordering."""

from pathlib import Path

from src.agent.catalogue import build_registry
from src.evaluation.model_policy import require_evaluated_model
from src.model_routing import configured_routes
from src.runtime_config import (
    UnsafeProductionConfigurationError,
    is_production,
    validate_model_routes,
    validate_settings,
    warn_participant_pins,
)
from src.schema import EXPECTED_SCHEMA_VERSION

_ROOT = Path(__file__).resolve().parents[1]


def validate_runtime_configuration(config: object) -> None:
    """The whole startup gate: reject unsafe settings, then unevaluated model routes.

    One call, made by ``main`` and ``cli`` before any side effect. Privacy decision 04:
    MODE_MODELS and a non-Gemini default need current per-Mode evaluation evidence in production.
    """
    # Routes, their evidence, the pins notice, then every other setting: HEAD's order.
    validate_model_routes(config)
    _require_mode_evidence(config)
    warn_participant_pins(config)
    validate_settings(config)


def _require_mode_evidence(config: object) -> None:
    default, _dev, modes, _pins = configured_routes(config)
    if modes:
        registry = build_registry()
        if set(modes) - {mode.id for mode in registry}:
            raise UnsafeProductionConfigurationError("MODE_MODELS names an unknown Mode")
        if is_production(config):
            for mode_id, model in modes.items():
                try:
                    require_evaluated_model(registry[mode_id], model, _ROOT)
                except ValueError:
                    raise UnsafeProductionConfigurationError(
                        "MODE_MODELS requires current passing per-Mode/model evaluation evidence"
                    ) from None
    if is_production(config) and not default.startswith("google:"):
        # Gate A certifies the Gemini path; another default needs evidence per live Mode.
        for mode in build_registry():
            if mode.status == "live" and mode.id not in modes:
                try:
                    require_evaluated_model(mode, default, _ROOT)
                except ValueError:
                    raise UnsafeProductionConfigurationError(
                        "A non-Gemini DEFAULT_MODEL requires passing evaluation evidence "
                        "for every live Mode"
                    ) from None




async def initialize_runtime(store, scheduler, outbox) -> None:
    """Verify the exact schema before starting scheduler-owned side effects."""
    await store.connect()
    await store.verify_schema_version(EXPECTED_SCHEMA_VERSION)
    scheduler.start()
    scheduler.start_outbox_worker(outbox.drain_once)
    scheduler.start_reconciliation(scheduler.reconcile)
    await outbox.drain_once()
    await scheduler.reload_pending()
