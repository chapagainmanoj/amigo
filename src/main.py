"""FastAPI app — Telegram webhook endpoint + lifecycle management."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.activation import router as activation_router
from src.api.channels import router as channels_router
from src.api.coaching import router as coaching_router
from src.api.dashboard import router as dashboard_router
from src.api.dependencies import get_activated_user
from src.api.memory import router as memory_router
from src.api.mode_suggestions import router as mode_suggestions_router
from src.api.modes import router as modes_router
from src.api.pairing import router as pairing_router
from src.api.reminders import router as reminders_router
from src.api.tasks import router as tasks_router
from src.bot.handlers import BotHandlers
from src.bot.update_claims import ChannelUpdateCoordinator, participant_key
from src.channels.registry import ChannelRegistry
from src.channels.telegram import TelegramChannel
from src.config import settings
from src.maintenance import run_isolated_steps
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.mode_readiness import coach_readiness
from src.observability import monitor_event_loop_delay, quiet_routine_logs
from src.reliability import assess_readiness
from src.runtime_config import (
    is_production,
    require_agent_credentials,
    validate_runtime_configuration,
)
from src.scheduler.coaching import CoachingDeliveryWorker
from src.scheduler.outbox import SchedulerOutboxWorker
from src.scheduler.reminders import ReminderScheduler
from src.startup import initialize_runtime

validate_runtime_configuration(settings)

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
# httpx logs every request URL at INFO, and Telegram Bot API URLs embed the bot token.
for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
# Only staging performance evidence needs routine logs; LOG_LEVEL=DEBUG brings them back.
if settings.app_env.strip().lower() != "staging" and settings.log_level != "DEBUG":
    quiet_routine_logs()
logger = logging.getLogger(__name__)

# ── Wiring ──
channel = TelegramChannel()
# Every channel this process runs; proactive messages use each participant's primary one.
channels = ChannelRegistry([channel])
store = MemoryStore()
session_mgr = SessionManager(store)
reminder_scheduler = ReminderScheduler(channel=channels, store=store)
outbox_worker = SchedulerOutboxWorker(store, reminder_scheduler)
handlers = BotHandlers(
    channel=channel,
    store=store,
    session_mgr=session_mgr,
    reminder_scheduler=reminder_scheduler,
    channels=channels,
)
update_coordinator = ChannelUpdateCoordinator(store)
# One BotHandlers per channel; all share the store, scheduler and the one Turn serializer.
handlers_by_channel = {channel.channel_id: handlers}
coaching_worker = CoachingDeliveryWorker(
    store, channels, admission_check=coach_readiness.complete
)

# Unknown until getMe succeeds for the configured token. Never seeded with a literal
# handle: a default would name the production bot from every other environment.
bot_username: str | None = None


async def _recover_pending_handoffs() -> None:
    """Recovery uses the same recipient lock as webhook Turns, without recursive locking.

    Each channel's controller recovers only participants whose primary channel it is.
    """
    for channel_handlers in handlers_by_channel.values():
        await channel_handlers.handoffs.recover(update_coordinator.serializer)


async def _close_expired_modes() -> None:
    for channel_handlers in handlers_by_channel.values():
        await channel_handlers.turn_processor.modes.conversations.close_expired()


async def _refresh_coach_admission():
    coaching_worker.admission_enabled = False
    coaching_worker.admission_enabled = await coach_readiness.complete()


async def _maintain_modes():
    await run_isolated_steps([
        ("memory_prune", handlers.memory.service.prune),
        ("close_expired_modes", _close_expired_modes),
        ("handoff_recovery", _recover_pending_handoffs),
        ("coach_readiness", _refresh_coach_admission),
        ("coach_reconcile", coaching_worker.reconcile),
        ("coach_delivery", coaching_worker.drain_once),
    ])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop scheduler and set Telegram webhook on app lifecycle."""
    global bot_username
    # Startup. Checked here rather than at import: this module is imported during test
    # collection, which never runs an agent, but a process that reaches lifespan intends to.
    require_agent_credentials(settings)
    # Establish capabilities before schedulers can deliver any message.
    bot_username = await channel.initialize(production=is_production(settings))
    app.state.bot_username = bot_username
    await initialize_runtime(store, reminder_scheduler, outbox_worker)

    await reminder_scheduler.start_mode_maintenance(_maintain_modes)

    # Set webhook
    try:
        webhook_url = f"{settings.app_base_url}/webhook"
        await channel.bot.set_webhook(
            url=webhook_url,
            secret_token=settings.telegram_webhook_secret,
        )
        logger.info("Webhook set to %s", webhook_url)

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
        # The webhook is deliberately left registered. During a rolling deploy the old instance
        # stops after the new one has set it, and an idle spin-down must stay wakeable by
        # Telegram; deleting it here would leave the bot unreachable.


app = FastAPI(title="Amigo", lifespan=lifespan)
app.state.store = store
app.state.channel = channel
app.state.bot_username = bot_username
app.state.memory_service = handlers.memory.service


async def _open_mode(user, mode_id, *, note=None):
    """Dashboard Mode switch on the participant's primary channel, under the Turn lock."""
    primary = channels.for_user(user)
    if primary is None:
        return None
    recipient = await primary.recipient_for(user)
    if recipient is None:
        return None
    primary_handlers = handlers_by_channel[primary.channel_id]
    async with update_coordinator.serializer.hold(participant_key(user)):
        return await primary_handlers.turn_processor.open_mode(
            recipient, user, mode_id, note=note
        )


app.state.open_mode = _open_mode
app.include_router(activation_router)
app.include_router(dashboard_router)
app.include_router(pairing_router)
app.include_router(tasks_router)
app.include_router(reminders_router)
app.include_router(modes_router)
app.include_router(mode_suggestions_router)
app.include_router(channels_router)
app.include_router(coaching_router)
app.include_router(memory_router)

# CORS Setup
origins = [
    settings.dashboard_url,
]
if not is_production(settings):
    origins.extend(["http://localhost:5173", "http://localhost:3000"])

RETRYABLE_HEADERS = ["X-Retryable"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The dashboard is always a different origin from the API, so any response header it has
    # to read must be named here. Without this the browser hides X-Retryable entirely and the
    # Activation retry silently never happens.
    expose_headers=RETRYABLE_HEADERS,
)


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Receive Telegram updates via webhook."""
    # Verify secret token
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    data = await request.json()
    update = await channel.decode_update(data)
    if update is None:
        return {"ok": True}

    if update.kind == "message":

        async def process_message() -> None:
            await handlers.handle_message(
                chat_id=update.chat_id,
                text=update.text,
                update_id=update.update_id,
                conversation=update.conversation,
            )

        result = await update_coordinator.run(
            update_id=update.update_id,
            chat_id=update.chat_id,
            update_kind="message",
            process=process_message,
        )
        return {"ok": True, "outcome": result.outcome}

    if update.kind == "callback_query":

        async def process_callback() -> None:
            await handlers.handle_callback(
                chat_id=update.chat_id,
                message_id=update.message_id,
                data=update.data,
                conversation=update.conversation,
            )

        async def acknowledge() -> None:
            await channel.acknowledge_callback(update.callback_id)

        result = await update_coordinator.run(
            update_id=update.update_id,
            chat_id=update.chat_id,
            update_kind="callback_query",
            process=process_callback,
            acknowledge=acknowledge,
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
