"""Fail-closed runtime configuration validation."""

import re
from collections.abc import Iterable
from urllib.parse import urlsplit


class UnsafeProductionConfigurationError(RuntimeError):
    """Raised when production configuration is missing or unsafe."""


# ACCESS_MODE postures (the Literal on ``Settings.access_mode`` lists the same values).
ACCESS_OPEN = "open"
ACCESS_CLOSED = "closed"
ACCESS_ALLOWLIST = "allowlist"
ACCESS_REGISTERED = frozenset({"registered", "invite"})  # "invite" is the legacy alias


def is_production(config: object) -> bool:
    """Return whether the configured environment is production."""
    return str(getattr(config, "app_env", "")).strip().lower() == "production"


def parse_allowed_chat_ids(raw_value: str) -> set[int]:
    """Parse a comma-separated Telegram allowlist without accepting ambiguous values."""
    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    try:
        chat_ids = {int(value) for value in values}
    except ValueError as error:
        raise UnsafeProductionConfigurationError(
            "ALLOWED_TELEGRAM_CHAT_IDS must contain only comma-separated integers"
        ) from error
    if any(chat_id <= 0 for chat_id in chat_ids):
        raise UnsafeProductionConfigurationError(
            "ALLOWED_TELEGRAM_CHAT_IDS must contain only positive integers"
        )
    return chat_ids


def require_agent_credentials(config: object) -> None:
    """Reject a missing model key before an entry point starts serving.

    GOOGLE_API_KEY has no default on Settings any more, so pydantic no longer refuses to build a
    configuration without one. That is deliberate — importing a module must not need a secret —
    but it means every environment, not just production, has to check for itself at the point it
    actually intends to run. Call this from an entry point, never at import: `src.main` is
    imported during test collection, which never talks to a model.

    Without it a missing key surfaces as the agent's friendly "having trouble thinking" reply,
    which reads like a model outage rather than a configuration error.
    """
    dev_model = str(getattr(config, "dev_model", "")).strip()
    if dev_model and is_production(config):
        _invalid("DEV_MODEL", "is development-only")
    if dev_model.startswith(("claude-cli:", "ollama:")):
        if not dev_model.partition(":")[2].strip():
            raise UnsafeProductionConfigurationError("DEV_MODEL requires a model name")
        return
    for setting in _required_key_settings(config):
        if not str(getattr(config, setting, "")).strip():
            raise UnsafeProductionConfigurationError(
                f"{setting.upper()} is required to run the agent. "
                "Set it in .env or the environment."
            )


def _routed_providers(config: object, *, include_pins: bool = True) -> set[str]:
    from src.model_routing import configured_routes, provider_of

    try:
        default, dev, modes, pins = configured_routes(config)
    except ValueError as error:
        raise UnsafeProductionConfigurationError(str(error)) from None
    if dev:
        return {provider_of(dev)}
    routes = [default, *modes.values(), *(pins.values() if include_pins else ())]
    return {provider_of(route) for route in routes}


def _required_key_settings(config: object) -> list[str]:
    from src.model_routing import PROVIDER_KEYS

    return sorted(
        {PROVIDER_KEYS[p] for p in _routed_providers(config) if p in PROVIDER_KEYS}
    )


def validate_runtime_configuration(config: object) -> None:
    """Reject unsafe production settings before startup creates any side effect."""
    _validate_model_routing(config)
    if getattr(config, "discord_enabled", False) is True:
        _require_secret(
            "DISCORD_BOT_TOKEN", getattr(config, "discord_bot_token", ""), minimum_length=50
        )
    if not is_production(config):
        return

    if str(getattr(config, "app_channel", "")).strip().lower() != "telegram":
        _invalid("APP_CHANNEL", "must be telegram in production")

    _require_telegram_bot_token(getattr(config, "telegram_bot_token", ""))
    _require_webhook_secret(getattr(config, "telegram_webhook_secret", ""))
    _require_https_origin("APP_BASE_URL", getattr(config, "app_base_url", ""))
    _require_https_origin("DASHBOARD_URL", getattr(config, "dashboard_url", ""))
    _require_https_origin("SUPABASE_URL", getattr(config, "supabase_url", ""))
    _require_secret(
        "SUPABASE_SERVICE_KEY",
        getattr(config, "supabase_service_key", ""),
        minimum_length=32,
    )
    for setting in _required_key_settings(config):
        _require_secret(setting.upper(), getattr(config, setting, ""), minimum_length=20)
    _require_non_placeholder("DEFAULT_MODEL", getattr(config, "default_model", ""))

    access_mode = str(getattr(config, "access_mode", "")).strip().lower()
    if access_mode == ACCESS_OPEN:
        _invalid("ACCESS_MODE", "cannot be open in production")
    if access_mode not in {ACCESS_CLOSED, ACCESS_ALLOWLIST, *ACCESS_REGISTERED}:
        _invalid("ACCESS_MODE", "must be closed, allowlist, or registered in production")
    if access_mode == ACCESS_ALLOWLIST and not parse_allowed_chat_ids(
        str(getattr(config, "allowed_telegram_chat_ids", ""))
    ):
        _invalid("ALLOWED_TELEGRAM_CHAT_IDS", "cannot be empty in allowlist mode")


def _require_secret(name: str, value: object, *, minimum_length: int) -> None:
    text = str(value).strip()
    if len(text) < minimum_length or _looks_like_placeholder(text):
        _invalid(name, "is missing or unsafe")


def _require_telegram_bot_token(value: object) -> None:
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]{6,}:[A-Za-z0-9_-]{20,}", text) or _looks_like_placeholder(text):
        _invalid("TELEGRAM_BOT_TOKEN", "is missing or unsafe")


def _require_webhook_secret(value: object) -> None:
    text = str(value).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", text) or _looks_like_placeholder(text):
        _invalid("TELEGRAM_WEBHOOK_SECRET", "is missing or unsafe")


def _require_non_placeholder(name: str, value: object) -> None:
    text = str(value).strip()
    if not text or _looks_like_placeholder(text):
        _invalid(name, "is missing or unsafe")


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.lower()
    markers: Iterable[str] = (
        "changeme",
        "example",
        "placeholder",
        "replace-me",
        "your-",
        "your_",
    )
    return any(marker in normalized for marker in markers)


def _require_https_origin(name: str, value: object) -> None:
    text = str(value).strip()
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
    ):
        _invalid(name, "must be a public HTTPS origin")


def _invalid(name: str, reason: str) -> None:
    raise UnsafeProductionConfigurationError(f"Invalid production setting {name}: {reason}")


def _validate_model_routing(config: object) -> None:
    from pathlib import Path

    from src.model_routing import configured_routes

    try:
        default, dev, modes, pins = configured_routes(config)
    except ValueError as error:
        raise UnsafeProductionConfigurationError(str(error)) from None
    if is_production(config):
        if dev:
            _invalid("DEV_MODEL", "is development-only")
        approved = {
            entry.strip().lower()
            for entry in str(getattr(config, "approved_model_providers", "google")).split(",")
            if entry.strip()
        }
        # Owner pins are exempt: they route only owner/internal dogfooding accounts.
        if _routed_providers(config, include_pins=False) - approved:
            _invalid(
                "APPROVED_MODEL_PROVIDERS",
                "must list every DEFAULT_MODEL/MODE_MODELS provider (privacy decision 04)",
            )
        if any(
            model.startswith("claude-cli:") for model in [default, *modes.values(), *pins.values()]
        ):
            _invalid("model routing", "Claude CLI is development-only")
    if modes:
        from src.agent.catalogue import build_registry

        registry = build_registry()
        if set(modes) - {mode.id for mode in registry}:
            raise UnsafeProductionConfigurationError("MODE_MODELS names an unknown Mode")
        if is_production(config):
            from src.evaluation.model_policy import require_evaluated_model

            root = Path(__file__).resolve().parents[1]
            for mode_id, model in modes.items():
                try:
                    require_evaluated_model(registry[mode_id], model, root)
                except ValueError:
                    raise UnsafeProductionConfigurationError(
                        "MODE_MODELS requires current passing per-Mode/model evaluation evidence"
                    ) from None
    if is_production(config) and not default.startswith("google:"):
        # Gate A certifies the Gemini path; another default needs evidence per live Mode.
        from src.agent.catalogue import build_registry
        from src.evaluation.model_policy import require_evaluated_model

        root = Path(__file__).resolve().parents[1]
        registry = build_registry()
        for mode in registry:
            if mode.status == "live" and mode.id not in modes:
                try:
                    require_evaluated_model(mode, default, root)
                except ValueError:
                    raise UnsafeProductionConfigurationError(
                        "A non-Gemini DEFAULT_MODEL requires passing evaluation evidence "
                        "for every live Mode"
                    ) from None
    if pins:
        import logging

        logging.getLogger(__name__).warning(
            "participant_model_pins restricted to owner/internal dogfooding accounts count=%d",
            len(pins),
        )
