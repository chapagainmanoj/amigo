"""Onboarding state machine tests.

Test #4 from the grill list — covers the full onboarding flow:
- New user welcome
- Name capture
- Timezone auto-confirm, manual entry, alias mapping, invalid rejection
- Completion consumption (test #14)
"""

import pytest

from src.bot.onboarding import TIMEZONE_ALIASES, handle_onboarding
from tests.fakes import FakeChannel, FakeStore


@pytest.fixture
def channel():
    return FakeChannel()


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
async def new_user(store):
    return await store.create_user(12345)


class TestOnboardingWelcome:
    """Step 0 → Step 1: welcome message and name prompt."""

    @pytest.mark.asyncio
    async def test_new_user_gets_welcome(self, channel, store, new_user):
        result = await handle_onboarding(new_user, "hi", channel, store, 12345)

        assert result is True  # still onboarding
        assert "Amigo" in channel.last_text
        assert "call you" in channel.last_text
        # Step should advance to 1
        updated = await store.get_user_by_chat_id(12345)
        assert updated["onboarding_step"] == 1


class TestOnboardingName:
    """Step 1 → Step 2: name capture and timezone confirmation."""

    @pytest.mark.asyncio
    async def test_name_stored_and_timezone_shown(self, channel, store, new_user):
        # Advance to step 1
        new_user["onboarding_step"] = 1
        await store.update_user(new_user["user_id"], {"onboarding_step": 1})

        result = await handle_onboarding(new_user, "Mano", channel, store, 12345)

        assert result is True
        updated = await store.get_user_by_chat_id(12345)
        assert updated["name"] == "Mano"
        assert updated["onboarding_step"] == 2
        assert "Kathmandu" in channel.last_text
        # Should have timezone confirm buttons
        assert channel.sent[-1]["buttons"] is not None


class TestOnboardingTimezone:
    """Step 2: timezone confirmation — auto, manual, alias, invalid."""

    @pytest.mark.asyncio
    async def test_confirm_default_timezone(self, channel, store, new_user):
        new_user["onboarding_step"] = 2
        await store.update_user(new_user["user_id"], {"onboarding_step": 2})

        result = await handle_onboarding(
            new_user, "", channel, store, 12345, callback_data="tz:confirm"
        )

        assert result is False  # onboarding complete
        updated = await store.get_user_by_chat_id(12345)
        assert updated["timezone"] == "Asia/Kathmandu"
        assert updated["onboarding_complete"] is True
        assert "planning" in channel.last_text.lower()

    @pytest.mark.asyncio
    async def test_manual_timezone_prompt(self, channel, store, new_user):
        new_user["onboarding_step"] = 2
        await store.update_user(new_user["user_id"], {"onboarding_step": 2})

        result = await handle_onboarding(
            new_user, "", channel, store, 12345, callback_data="tz:manual"
        )

        assert result is True  # still on step 2
        assert "timezone" in channel.last_text.lower()

    @pytest.mark.asyncio
    async def test_manual_valid_timezone(self, channel, store, new_user):
        new_user["onboarding_step"] = 2
        await store.update_user(new_user["user_id"], {"onboarding_step": 2})

        result = await handle_onboarding(
            new_user, "America/Toronto", channel, store, 12345
        )

        assert result is False  # complete
        updated = await store.get_user_by_chat_id(12345)
        assert updated["timezone"] == "America/Toronto"
        assert updated["onboarding_complete"] is True

    @pytest.mark.asyncio
    async def test_timezone_alias_mapping(self, channel, store, new_user):
        """Typing 'nepal' should resolve to Asia/Kathmandu."""
        new_user["onboarding_step"] = 2
        await store.update_user(new_user["user_id"], {"onboarding_step": 2})

        result = await handle_onboarding(new_user, "nepal", channel, store, 12345)

        assert result is False
        updated = await store.get_user_by_chat_id(12345)
        assert updated["timezone"] == "Asia/Kathmandu"

    @pytest.mark.asyncio
    async def test_invalid_timezone_rejected(self, channel, store, new_user):
        """Invalid timezone should stay on step 2 with helpful message."""
        new_user["onboarding_step"] = 2
        await store.update_user(new_user["user_id"], {"onboarding_step": 2})

        result = await handle_onboarding(new_user, "EST", channel, store, 12345)

        assert result is True  # still onboarding
        assert "doesn't look right" in channel.last_text
        # Should still be on step 2
        updated = await store.get_user_by_chat_id(12345)
        assert updated["onboarding_step"] == 2


class TestOnboardingCompletion:
    """Test #14: onboarding completion message."""

    @pytest.mark.asyncio
    async def test_completion_message_is_planning_prompt(self, channel, store, new_user):
        """Final message should ask about today's plans."""
        new_user["onboarding_step"] = 2
        new_user["name"] = "Mano"
        await store.update_user(new_user["user_id"], {
            "onboarding_step": 2, "name": "Mano"
        })

        await handle_onboarding(
            new_user, "", channel, store, 12345, callback_data="tz:confirm"
        )

        assert "Mano" in channel.last_text
        assert "planning" in channel.last_text.lower() or "today" in channel.last_text.lower()


class TestTimezoneAliases:
    """Verify all documented aliases are valid IANA timezones."""

    def test_all_aliases_are_valid(self):
        from zoneinfo import ZoneInfo
        for alias, tz_name in TIMEZONE_ALIASES.items():
            try:
                ZoneInfo(tz_name)
            except KeyError:
                pytest.fail(f"Alias '{alias}' maps to invalid timezone '{tz_name}'")
