"""CLI implementation of MessageChannel — chat in your terminal."""

import logging
from itertools import count

logger = logging.getLogger(__name__)

# ANSI escape helpers
_CYAN = "\033[96m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_YELLOW = "\033[93m"
_RESET = "\033[0m"

# Auto-incrementing message IDs (no Telegram to provide them)
_msg_counter = count(1)


class CLIChannel:
    """Terminal-based MessageChannel for local development.

    - send_message() prints to stdout with colored formatting.
    - Inline buttons render as numbered options; the CLI entrypoint
      translates numeric input into callback_data.
    - pending_buttons tracks the most recent button set for dispatch.
    """

    def __init__(self):
        # Last set of buttons sent, so the input loop can resolve "1" → callback_data
        self.pending_buttons: list[dict[str, str]] = []
        self._pending_message_id: int | None = None

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> int | None:
        """Print a message to the terminal, optionally with numbered button choices."""
        msg_id = next(_msg_counter)

        print(f"\n{_CYAN}{_BOLD}Amigo:{_RESET} {text}")

        if buttons:
            flat = [btn for row in buttons for btn in row]
            self.pending_buttons = flat
            self._pending_message_id = msg_id
            print(f"{_DIM}  ──────────────────────────{_RESET}")
            for i, btn in enumerate(flat, 1):
                print(f"  {_YELLOW}[{i}]{_RESET} {btn['text']}")
            print(f"{_DIM}  (type a number to tap a button){_RESET}")
        else:
            # No new buttons — clear any stale ones
            self.pending_buttons = []
            self._pending_message_id = None

        return msg_id

    async def edit_message_buttons(
        self,
        chat_id: str | int,
        message_id: int,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> None:
        """Edit buttons on a previous message.

        Terminal is append-only, so we just clear the pending state
        or print new buttons.
        """
        if buttons is None:
            # Buttons removed — clear pending
            if self._pending_message_id == message_id:
                self.pending_buttons = []
                self._pending_message_id = None
        else:
            flat = [btn for row in buttons for btn in row]
            self.pending_buttons = flat
            self._pending_message_id = message_id
            print(f"\n{_DIM}  [buttons updated]{_RESET}")
            for i, btn in enumerate(flat, 1):
                print(f"  {_YELLOW}[{i}]{_RESET} {btn['text']}")

    def resolve_button(self, choice: str) -> str | None:
        """Resolve a numeric choice to callback_data. Returns None if invalid."""
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(self.pending_buttons):
                data = self.pending_buttons[idx]["callback_data"]
                self.pending_buttons = []
                self._pending_message_id = None
                return data
        except (ValueError, IndexError):
            pass
        return None
