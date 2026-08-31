"""FastAPI app — Telegram webhook endpoint + lifecycle management."""

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from telegram import Update

from src.api.dashboard import router as dashboard_router
from src.api.reminders import router as reminders_router
from src.api.tasks import router as tasks_router
from src.auth import get_authenticated_user_id
from src.bot.handlers import BotHandlers
from src.bot.update_claims import TelegramUpdateCoordinator
from src.channels.telegram import TelegramChannel
from src.config import settings
from src.memory.pairing import (
    PAIRING_TOKEN_HEX_LENGTH,
    PAIRING_TOKEN_TTL,
    PAIRING_TOKEN_WINDOW,
    PairingTokenRateLimitError,
)
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.runtime_config import is_production, validate_runtime_configuration
from src.scheduler.outbox import SchedulerOutboxWorker
from src.scheduler.reminders import ReminderScheduler
from src.utils import utc_now

validate_runtime_configuration(settings)

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── Wiring ──
channel = TelegramChannel()
store = MemoryStore()
session_mgr = SessionManager(store)
reminder_scheduler = ReminderScheduler(channel=channel, store=store)
outbox_worker = SchedulerOutboxWorker(store, reminder_scheduler)
handlers = BotHandlers(
    channel=channel,
    store=store,
    session_mgr=session_mgr,
    reminder_scheduler=reminder_scheduler,
)
update_coordinator = TelegramUpdateCoordinator(store)

bot_username = "amigo_agent_bot"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop scheduler and set Telegram webhook on app lifecycle."""
    global bot_username
    # Startup
    reminder_scheduler.start()
    reminder_scheduler.start_outbox_worker(outbox_worker.drain_once)
    await outbox_worker.drain_once()
    await reminder_scheduler.reload_pending()

    # Set webhook
    try:
        webhook_url = f"{settings.app_base_url}/webhook"
        await channel.bot.set_webhook(
            url=webhook_url,
            secret_token=settings.telegram_webhook_secret,
        )
        logger.info("Webhook set to %s", webhook_url)

        bot_info = await channel.bot.get_me()
        bot_username = bot_info.username
        logger.info("Fetched bot username: %s", bot_username)
    except Exception as e:
        if is_production(settings):
            reminder_scheduler.shutdown()
            raise RuntimeError("Telegram webhook initialization failed") from None
        logger.warning("Failed to initialize Telegram webhook/bot info: %s", e)

    yield

    # Shutdown
    reminder_scheduler.shutdown()
    try:
        await channel.bot.delete_webhook()
    except Exception as e:
        logger.warning("Failed to delete Telegram webhook: %s", e)


app = FastAPI(title="Amigo", lifespan=lifespan)
app.state.store = store
app.include_router(dashboard_router)
app.include_router(tasks_router)
app.include_router(reminders_router)

# CORS Setup
origins = [
    settings.dashboard_url,
]
if not is_production(settings):
    origins.extend(["http://localhost:5173", "http://localhost:3000"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Receive Telegram updates via webhook."""
    # Verify secret token
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    data = await request.json()
    update = Update.de_json(data, channel.bot)

    if update.message and update.message.text:
        message = update.message

        async def process_message() -> None:
            await handlers.handle_message(
                chat_id=message.chat_id,
                text=message.text,
                update_id=update.update_id,
            )

        result = await update_coordinator.run(
            update_id=update.update_id,
            chat_id=message.chat_id,
            update_kind="message",
            process=process_message,
        )
        return {"ok": True, "outcome": result.outcome}

    if update.callback_query:
        query = update.callback_query

        async def process_callback() -> None:
            await handlers.handle_callback(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                data=query.data,
            )

        result = await update_coordinator.run(
            update_id=update.update_id,
            chat_id=query.message.chat_id,
            update_kind="callback_query",
            process=process_callback,
            acknowledge=query.answer,
        )
        return {"ok": True, "outcome": result.outcome}

    return {"ok": True}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "env": settings.app_env}


@app.post("/api/pairing-token")
async def get_pairing_token(auth_id: str = Depends(get_authenticated_user_id)):
    """Generate a pairing token for Telegram account linking."""
    if settings.access_mode == "closed":
        raise HTTPException(status_code=503, detail="New Pairing links are temporarily disabled.")
    if await store.get_user_by_auth_id(auth_id):
        raise HTTPException(status_code=409, detail="Dashboard account is already linked.")

    token = secrets.token_hex(PAIRING_TOKEN_HEX_LENGTH // 2)
    expires_at = utc_now() + PAIRING_TOKEN_TTL
    try:
        await store.create_pairing_token(token, auth_id, expires_at)
    except PairingTokenRateLimitError:
        raise HTTPException(
            status_code=429,
            detail="Too many Pairing links requested. Try again later.",
            headers={"Retry-After": str(int(PAIRING_TOKEN_WINDOW.total_seconds()))},
        ) from None
    bot_link = f"https://t.me/{bot_username}?start=pair_{token}"
    return {
        "token": token,
        "bot_link": bot_link,
        "expires_at": expires_at.isoformat(),
    }


@app.get("/api/me")
async def get_me(auth_id: str = Depends(get_authenticated_user_id)):
    """Return the user profile corresponding to the authenticated user."""
    user = await store.get_user_by_auth_id(auth_id)
    if not user:
        raise HTTPException(
            status_code=404, detail="User profile not paired with Telegram yet."
        )
    return user
