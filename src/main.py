"""FastAPI app — Telegram webhook endpoint + lifecycle management."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from telegram import Update

from src.bot.handlers import BotHandlers
from src.channels.telegram import TelegramChannel
from src.config import settings
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler

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
handlers = BotHandlers(
    channel=channel,
    store=store,
    session_mgr=session_mgr,
    reminder_scheduler=reminder_scheduler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop scheduler and set Telegram webhook on app lifecycle."""
    # Startup
    reminder_scheduler.start()
    await reminder_scheduler.reload_pending()

    # Set webhook
    webhook_url = f"{settings.app_base_url}/webhook"
    await channel.bot.set_webhook(
        url=webhook_url,
        secret_token=settings.telegram_webhook_secret,
    )
    logger.info("Webhook set to %s", webhook_url)

    yield

    # Shutdown
    reminder_scheduler.shutdown()
    await channel.bot.delete_webhook()


app = FastAPI(title="Amigo", lifespan=lifespan)


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
        await handlers.handle_message(
            chat_id=update.message.chat_id,
            text=update.message.text,
        )

    elif update.callback_query:
        query = update.callback_query
        await query.answer()  # Acknowledge immediately
        await handlers.handle_callback(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            data=query.data,
        )

    return {"ok": True}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "env": settings.app_env}
