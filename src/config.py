"""Application configuration via environment variables."""

from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All config from .env — fails fast if required vars are missing."""

    # Channel selection — "telegram" (default) or "cli"
    app_channel: str = "telegram"

    # Telegram (required when app_channel=telegram, ignored in cli mode)
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # Supabase (required when app_channel=telegram, ignored in cli mode)
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Google AI (required in production; enforced by validate_runtime_configuration)
    #
    # Defaults to "" like every other secret here. Being the one field pydantic itself required
    # meant constructing Settings at all needed a key, which defeated LazySettings: importing
    # src.main during test collection loaded settings for real and aborted the run. Production
    # safety is unchanged — runtime_config requires a 20+ character value whenever APP_ENV is
    # production, exactly as it does for SUPABASE_SERVICE_KEY and the Telegram secrets.
    google_api_key: str = ""

    # App
    app_base_url: str = "http://localhost:8000"
    dashboard_url: str = "http://localhost:5173"
    app_env: str = "development"
    log_level: str = "INFO"

    # Access control — open is development-only; production must choose a closed posture
    access_mode: Literal["open", "closed", "allowlist", "invite"] = "open"
    allowed_telegram_chat_ids: str = ""  # e.g. "123456789,987654321"

    # LLM defaults
    default_model: str = "gemini-3.5-flash"
    dev_model: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    mode_models: dict[str, str] | str = {}
    participant_model_pins: dict[str, str] | str = {}
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    # Providers the owner has approved as participant-data processors in production. Adding one
    # is a privacy decision (decision 04): update the notice and consent before listing it.
    approved_model_providers: str = "google"

    @field_validator("mode_models", "participant_model_pins", mode="before")
    @classmethod
    def _model_map(cls, value, info):
        from src.model_routing import parse_model_map

        return parse_model_map(value, setting=info.field_name.upper())

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "hide_input_in_errors": True}


class LazySettings:
    """Load settings on first attribute access, not module import.

    This keeps test collection from requiring production secrets while
    preserving fail-fast behavior when the app actually reads configuration.
    """

    def __init__(self):
        self._settings: Settings | None = None

    def _load(self) -> Settings:
        if self._settings is None:
            self._settings = Settings()
        return self._settings

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._load(), name)


settings = LazySettings()
