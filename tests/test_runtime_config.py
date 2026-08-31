"""Production configuration must fail before startup side effects."""

from types import SimpleNamespace

import pytest

from src.config import Settings
from src.runtime_config import (
    UnsafeProductionConfigurationError,
    parse_allowed_chat_ids,
    validate_runtime_configuration,
)


def _production_config(**overrides) -> SimpleNamespace:
    values = {
        "app_env": "production",
        "app_channel": "telegram",
        "telegram_bot_token": "123456789:" + ("A" * 35),
        "telegram_webhook_secret": "w" * 32,
        "app_base_url": "https://api.amigo.test",
        "dashboard_url": "https://app.amigo.test",
        "supabase_url": "https://amigo.supabase.co",
        "supabase_service_key": "s" * 40,
        "google_api_key": "g" * 30,
        "default_model": "gemini-test-model",
        "access_mode": "allowlist",
        "allowed_telegram_chat_ids": "111,222",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("setting", "overrides"),
    [
        ("APP_CHANNEL", {"app_channel": "cli"}),
        ("TELEGRAM_BOT_TOKEN", {"telegram_bot_token": ""}),
        ("TELEGRAM_BOT_TOKEN", {"telegram_bot_token": "x" * 40}),
        ("TELEGRAM_WEBHOOK_SECRET", {"telegram_webhook_secret": "short"}),
        ("TELEGRAM_WEBHOOK_SECRET", {"telegram_webhook_secret": "contains spaces" * 3}),
        ("APP_BASE_URL", {"app_base_url": "http://localhost:8000"}),
        ("DASHBOARD_URL", {"dashboard_url": "http://localhost:5173"}),
        ("DASHBOARD_URL", {"dashboard_url": "https://app.amigo.test/path"}),
        ("SUPABASE_URL", {"supabase_url": "http://amigo.supabase.co"}),
        ("SUPABASE_SERVICE_KEY", {"supabase_service_key": "your-service-key"}),
        ("GOOGLE_API_KEY", {"google_api_key": ""}),
        ("DEFAULT_MODEL", {"default_model": ""}),
        ("ACCESS_MODE", {"access_mode": "open"}),
        ("ACCESS_MODE", {"access_mode": "unexpected"}),
        ("ALLOWED_TELEGRAM_CHAT_IDS", {"allowed_telegram_chat_ids": ""}),
        ("ALLOWED_TELEGRAM_CHAT_IDS", {"allowed_telegram_chat_ids": "111,not-an-id"}),
    ],
)
def test_unsafe_production_setting_is_rejected(setting, overrides):
    with pytest.raises(UnsafeProductionConfigurationError, match=setting):
        validate_runtime_configuration(_production_config(**overrides))


@pytest.mark.parametrize("access_mode", ["closed", "allowlist", "invite"])
def test_valid_production_configuration_is_accepted(access_mode):
    overrides = {"access_mode": access_mode}
    if access_mode != "allowlist":
        overrides["allowed_telegram_chat_ids"] = ""

    validate_runtime_configuration(_production_config(**overrides))


def test_failure_identifies_setting_without_secret_value():
    unsafe_secret = "this-is-a-secret-but-too-short"

    with pytest.raises(UnsafeProductionConfigurationError) as error:
        validate_runtime_configuration(
            _production_config(telegram_webhook_secret=unsafe_secret)
        )

    assert "TELEGRAM_WEBHOOK_SECRET" in str(error.value)
    assert unsafe_secret not in str(error.value)


def test_development_cli_keeps_minimal_configuration():
    config = Settings(
        _env_file=None,
        app_channel="cli",
        app_env="development",
        google_api_key="development-key",
    )

    validate_runtime_configuration(config)
    assert config.access_mode == "open"
    assert config.dashboard_url == "http://localhost:5173"


def test_allowlist_parser_rejects_non_positive_chat_ids():
    with pytest.raises(UnsafeProductionConfigurationError, match="ALLOWED_TELEGRAM_CHAT_IDS"):
        parse_allowed_chat_ids("111,-2")
