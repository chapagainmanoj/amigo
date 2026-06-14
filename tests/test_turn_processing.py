"""Turn processing integration tests."""

from datetime import timedelta
from unittest.mock import patch

from src.agent.amigo import AmigoAgent
from src.bot.handlers import BotHandlers
from src.memory.sessions import SessionManager
from src.utils import now_in_tz
from tests.fakes import FakeChannel, FakeModel, FakeScheduler, FakeStore


def _future_hhmm(timezone: str) -> str:
    local_target = now_in_tz(timezone) + timedelta(minutes=10)
    return local_target.strftime("%H:%M")


async def test_task_message_creates_task_schedules_reminder_and_confirms():
    store = FakeStore()
    channel = FakeChannel()
    model = FakeModel()
    model.responses["ExtractionResult"] = {
        "tasks": [
            {
                "title": "Drink water",
                "category": "health",
                "reminder_time": "in 10 minutes",
                "priority": "normal",
                "raw_input": "drink water in 10 minutes",
            }
        ],
        "unextracted": None,
        "confirmation_message": "Got it — drink water in 10 minutes.",
    }
    model.responses["ReminderTimeResolution"] = {
        "original": "in 10 minutes",
        "resolved_time": _future_hhmm("Asia/Kathmandu"),
        "confidence": "medium",
    }
    agent = AmigoAgent(model, store)
    scheduler = FakeScheduler()
    handlers = BotHandlers(agent, channel, store, SessionManager(store), scheduler)
    user = await store.create_user(123)
    await store.update_user(
        user["user_id"],
        {
            "name": "Dev",
            "timezone": "Asia/Kathmandu",
            "onboarding_complete": True,
            "onboarding_step": 3,
        },
    )

    with patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True):
        await handlers.handle_message(123, "today I need to drink water in 10 minutes")

    assert len(store.tasks) == 1
    assert store.tasks[0]["title"] == "Drink water"
    assert len(store.reminders) == 1
    assert len(scheduler.scheduled) == 1
    assert "drink water" in channel.last_text.lower()
