"""CBT research Mode: full-access only, crisis routing first, no Tools or Memory."""

import pytest

from src.access import entitled
from src.agent.catalogue import build_registry
from src.agent.modes import PLACEHOLDER_FACTS
from src.config import settings
from src.mode_readiness import reflect_safety_response
from tests.fakes import FakeStore

FULL, TRIAL = 111, 222


@pytest.fixture(autouse=True)
def _tiers(monkeypatch):
    monkeypatch.setattr(settings, "allowed_telegram_chat_ids", str(FULL))


async def _user(store, chat_id):
    user = await store.create_user(chat_id)
    await store.update_user(user["user_id"], {"timezone": "UTC", "onboarding_complete": True})
    return await store.get_user_by_chat_id(chat_id)


async def test_only_full_access_accounts_can_open_cbt():
    store, cbt = FakeStore(), build_registry()["cbt"]
    assert await entitled(store, await _user(store, FULL), cbt)
    assert not await entitled(store, await _user(store, TRIAL), cbt)


async def test_crisis_language_in_cbt_gets_the_fixed_referral_before_the_model():
    assert await reflect_safety_response("cbt", "I am thinking about killing myself") is not None
    assert await reflect_safety_response("cbt", "my friend hasn't replied") is None


def test_cbt_has_no_tools_or_context_and_states_its_limits():
    cbt = build_registry()["cbt"]
    assert cbt.toolsets == () and cbt.context == ()
    assert cbt.entry_guard is not None
    prompt = cbt.instructions(PLACEHOLDER_FACTS)
    assert "not therapy" in prompt and "one question per reply" in prompt
    assert "not therapy" in cbt.intro()
