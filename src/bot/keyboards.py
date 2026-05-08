"""Inline keyboard builders for Telegram bot."""


def reminder_keyboard(reminder_id: str) -> list[list[dict[str, str]]]:
    """Build Done/Skip/Later inline keyboard for a reminder notification."""
    return [
        [
            {"text": "Done ✅", "callback_data": f"done:{reminder_id}"},
            {"text": "Skip ⏭️", "callback_data": f"skip:{reminder_id}"},
            {"text": "Later ⏰", "callback_data": f"later:{reminder_id}"},
        ]
    ]


def confirm_timezone_keyboard() -> list[list[dict[str, str]]]:
    """Onboarding: confirm auto-detected timezone."""
    return [
        [
            {"text": "Yes ✓", "callback_data": "tz:confirm"},
            {"text": "No, set manually", "callback_data": "tz:manual"},
        ]
    ]


def skip_keyboard(step: str) -> list[list[dict[str, str]]]:
    """Onboarding: skip optional step with defaults."""
    return [
        [
            {"text": "Sounds good 👍", "callback_data": f"onboard:skip:{step}"},
        ]
    ]
