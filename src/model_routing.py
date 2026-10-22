"""Operator-owned model references and precedence; contains no participant input or secrets."""

import logging
import re
from collections.abc import Mapping

logger = logging.getLogger(__name__)
_PROVIDERS = {"google", "google-gla", "anthropic", "ollama", "claude-cli"}
_MODE_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def normalize_model(reference: str, *, setting: str = "model") -> str:
    if not isinstance(reference, str) or not reference or reference != reference.strip():
        raise ValueError(f"{setting} requires a nonempty model reference")
    if reference.startswith("gemini-"):
        reference = f"google:{reference}"
    provider, separator, name = reference.partition(":")
    if (
        not separator
        or provider not in _PROVIDERS
        or not name
        or name.startswith("-")
        or any(char.isspace() for char in name)
    ):
        raise ValueError(f"{setting} has an unsupported provider or model reference")
    return reference


def parse_model_map(value: object, *, setting: str) -> dict[str, str]:
    if value == "" or value is None:
        return {}
    entries = value.items() if isinstance(value, Mapping) else None
    if isinstance(value, str):
        pairs = [entry.strip().partition("=") for entry in value.split(",")]
        if any(not separator for _, separator, _ in pairs):
            raise ValueError(f"{setting} requires key=model entries")
        entries = [(key.strip(), model.strip()) for key, _, model in pairs]
    if entries is None:
        raise ValueError(f"{setting} requires a model map")
    parsed = {}
    for key, reference in entries:
        if (
            not isinstance(key, str)
            or not key
            or key != key.strip()
            or any(char.isspace() for char in key)
            or key in parsed
            or (setting == "MODE_MODELS" and not _MODE_ID.fullmatch(key))
        ):
            raise ValueError(f"{setting} contains an invalid or duplicate key")
        parsed[key] = normalize_model(reference, setting=setting)
    return parsed


def configured_routes(config: object) -> tuple[str, str, dict[str, str], dict[str, str]]:
    default = normalize_model(getattr(config, "default_model", ""), setting="DEFAULT_MODEL")
    dev = getattr(config, "dev_model", "")
    dev = normalize_model(dev, setting="DEV_MODEL") if isinstance(dev, str) and dev else ""
    modes = getattr(config, "mode_models", {})
    pins = getattr(config, "participant_model_pins", {})
    modes = parse_model_map(modes, setting="MODE_MODELS")
    pins = parse_model_map(pins, setting="PARTICIPANT_MODEL_PINS")
    return default, dev, modes, pins


def resolve_model(config: object, *, mode_id: str, user_id: str | None = None) -> str:
    default, dev, modes, pins = configured_routes(config)
    if dev:
        return dev
    if user_id in pins:
        logger.warning("owner_internal_model_pin mode=%s model=%s", mode_id, pins[user_id])
        return pins[user_id]
    return modes.get(mode_id, default)
