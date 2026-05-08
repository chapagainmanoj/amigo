"""MessageChannel protocol — swap delivery channels without touching agent code."""

from typing import Protocol


class MessageChannel(Protocol):
    """Abstract interface for messaging channels.

    Agent sends messages through this without knowing if it's Telegram, WhatsApp, or native app.
    """

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> int | None:
        """Send a text message, optionally with inline keyboard buttons.

        Args:
            chat_id: Channel-specific user/chat identifier
            text: Message content
            buttons: Optional grid of buttons, each with "text" and "callback_data"
                     Example: [[{"text": "Done ✅", "callback_data": "done:uuid"}]]

        Returns:
            Message ID if available (for later editing), else None.
        """
        ...

    async def edit_message_buttons(
        self,
        chat_id: str | int,
        message_id: int,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> None:
        """Edit inline keyboard on an existing message. Pass buttons=None to remove keyboard."""
        ...
