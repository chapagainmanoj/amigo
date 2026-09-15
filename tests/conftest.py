"""Shared pytest configuration.

`tests/test_activation.py` imports `src.main`, and that module does two things at import scope —
`validate_runtime_configuration(settings)` and `logging.basicConfig(level=settings.log_level)` —
that both read settings. Either one defeats `LazySettings`, so `Settings()` loads for real during
collection and its one required field, `GOOGLE_API_KEY`, must be present.

A developer's gitignored `.env` supplies that locally, which is exactly why CI was the first place
this surfaced: the runner has no `.env`, so collection aborted before a single test ran.

Set a placeholder before any test module is imported. Environment variables outrank the `.env`
file in pydantic-settings' precedence, so this also stops a real key in someone's `.env` from
being loaded during a test run — tests drive the fakes in `tests/fakes.py` and must never reach a
live provider. An explicitly exported value is left alone.

Importing `src.main` also runs its module-level wiring, and `TelegramChannel()` constructs a
`Bot`, which rejects an empty token outright. `TELEGRAM_BOT_TOKEN` defaults to `""`, so that needs
a syntactically valid placeholder too — it is never dialled, only parsed.

None of these are credentials. Every other Settings field has a usable default.
"""

import os

PLACEHOLDER_ENV = {
    "GOOGLE_API_KEY": "test-key-not-a-real-credential",
    # python-telegram-bot parses the "<digits>:<alphanumeric>" shape at construction time.
    "TELEGRAM_BOT_TOKEN": "123456789:AAEtest-placeholder-token-not-real-000000000",
}

for name, placeholder in PLACEHOLDER_ENV.items():
    os.environ.setdefault(name, placeholder)
