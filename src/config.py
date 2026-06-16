"""Application configuration via environment variables."""

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

    # Google AI
    google_api_key: str

    # App
    app_base_url: str = "http://localhost:8000"
    app_env: str = "development"
    log_level: str = "INFO"

    # Access control — comma-separated Telegram chat IDs allowed to use the bot
    allowed_telegram_chat_ids: str = ""  # e.g. "123456789,987654321"

    # LLM defaults
    default_model: str = "gemini-3.5-flash"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


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
