# Review: Production Configuration Settings

Status: approved
Reviewer: project owner
Prepared: 2026-08-30

## Purpose

Issue 03 requires production to distinguish an intentionally open development bot from a closed
or invitation-controlled deployment. It also requires the dashboard origin to be part of typed
application configuration rather than being read independently in `src/main.py`.

The protected configuration change is deliberately small. Validation and access-control behavior
will live outside `src/config.py`; this file only introduces the two settings needed by that code.

## Exact proposed change to `src/config.py`

```diff
@@
 """Application configuration via environment variables."""
 
+from typing import Literal
+
 from pydantic_settings import BaseSettings
@@
     app_base_url: str = "http://localhost:8000"
+    dashboard_url: str = "http://localhost:5173"
     app_env: str = "development"
     log_level: str = "INFO"
 
-    # Access control — comma-separated Telegram chat IDs allowed to use the bot
+    # Access control — open is development-only; production must choose a closed posture
+    access_mode: Literal["open", "closed", "allowlist", "invite"] = "open"
     allowed_telegram_chat_ids: str = ""  # e.g. "123456789,987654321"
```

## Behavior built around these settings

- Production startup validation will reject `ACCESS_MODE=open` and accept only `closed`,
  `allowlist`, or `invite`.
- `allowlist` will require at least one valid positive Telegram chat ID.
- `closed` will reject Telegram messages and callbacks and will not issue new Pairing links.
- `invite` will admit valid Pairing deep links and already-paired Telegram profiles.
- Development keeps the current convenient `open` default.
- Production will also validate Telegram, webhook, Supabase, model, application URL, and dashboard
  origin values without logging their contents.
- Startup validation will run before the scheduler starts or webhook registration occurs, and a
  production webhook initialization failure will abort startup instead of being swallowed.

## Review checklist

- [x] The default remains convenient for development and tests.
- [x] Production cannot inherit the open default silently.
- [x] The four access-mode names are clear enough for deployment configuration.
- [x] `DASHBOARD_URL` belongs in typed Settings.
- [x] Validation remains outside the protected configuration module.

## Decision

Approved by the project owner on 2026-08-30.
