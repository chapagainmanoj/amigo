"""FastAPI app — Telegram webhook endpoint + lifecycle management."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from telegram import Update

from src.api.activation import router as activation_router
from src.api.dashboard import router as dashboard_router
from src.api.dependencies import get_activated_user
from src.api.pairing import router as pairing_router
from src.api.reminders import router as reminders_router
from src.api.tasks import router as tasks_router
from src.bot.handlers import BotHandlers
from src.bot.update_claims import TelegramUpdateCoordinator
from src.channels.telegram import TelegramChannel
from src.config import settings
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.observability import monitor_event_loop_delay
from src.reliability import assess_readiness
from src.runtime_config import is_production, validate_runtime_configuration
from src.scheduler.outbox import SchedulerOutboxWorker
from src.scheduler.reminders import ReminderScheduler
from src.startup import initialize_runtime

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
    await initialize_runtime(store, reminder_scheduler, outbox_worker)

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
        app.state.bot_username = bot_username
        logger.info("Fetched bot username: %s", bot_username)
    except Exception as e:
        if is_production(settings):
            reminder_scheduler.shutdown()
            raise RuntimeError("Telegram webhook initialization failed") from None
        logger.warning("Failed to initialize Telegram webhook/bot info: %s", e)

    monitor_stop = asyncio.Event()
    monitor_task = asyncio.create_task(
        monitor_event_loop_delay(monitor_stop),
        name="event-loop-delay-monitor",
    )
    try:
        yield
    finally:
        monitor_stop.set()
        await monitor_task
        reminder_scheduler.shutdown()
        try:
            await channel.bot.delete_webhook()
        except Exception as e:
            logger.warning("Failed to delete Telegram webhook: %s", e)


app = FastAPI(title="Amigo", lifespan=lifespan)
app.state.store = store
app.state.bot_username = bot_username
app.include_router(activation_router)
app.include_router(dashboard_router)
app.include_router(pairing_router)
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
    """Process liveness check; intentionally independent of dependencies."""
    return {"status": "ok", "env": settings.app_env}


@app.get("/ready")
async def readiness(request: Request):
    """Core Loop readiness based on database, scheduler, and outbox evidence."""
    payload, status_code = await assess_readiness(request.app.state.store)
    return JSONResponse(payload, status_code=status_code)


@app.get("/api/me")
async def get_me(user: Annotated[dict, Depends(get_activated_user)]):
    """Return the user profile corresponding to the authenticated user."""
    return user
