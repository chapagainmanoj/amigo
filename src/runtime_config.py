"""Fail-closed runtime configuration validation."""

import re
from collections.abc import Iterable
from urllib.parse import urlsplit


class UnsafeProductionConfigurationError(RuntimeError):
    """Raised when production configuration is missing or unsafe."""


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


def validate_runtime_configuration(config: object) -> None:
    """Reject unsafe production settings before startup creates any side effect."""
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
    _require_secret(
        "GOOGLE_API_KEY",
        getattr(config, "google_api_key", ""),
        minimum_length=20,
    )
    _require_non_placeholder("DEFAULT_MODEL", getattr(config, "default_model", ""))

    access_mode = str(getattr(config, "access_mode", "")).strip().lower()
    if access_mode == "open":
        _invalid("ACCESS_MODE", "cannot be open in production")
    if access_mode not in {"closed", "allowlist", "invite"}:
        _invalid("ACCESS_MODE", "must be closed, allowlist, or invite in production")
    if access_mode == "allowlist" and not parse_allowed_chat_ids(
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
