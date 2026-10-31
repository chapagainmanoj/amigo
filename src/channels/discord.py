"""Discord transport: gateway connection, DM addressing and event decoding stay here (ADR 0004).

Discord is the multi-app proof: it runs in the same process as Telegram, direct messages only,
for linked full-access accounts. Free-text DMs need the gateway (the HTTP interactions endpoint
only carries slash commands and components). Discord DMs have no threads, so Modes use the
in-chat command fallback.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

import discord

from src.channels.base import ChannelCapabilities, ConversationRef, IncomingUpdate

logger = logging.getLogger(__name__)

MESSAGE_LIMIT = 2000
BUTTONS_PER_ROW = 5
BUTTON_ROWS = 5
CUSTOM_ID_LIMIT = 100
LABEL_LIMIT = 80

_CAPABILITIES = ChannelCapabilities(
    actions=True,
    delivery_acknowledgement=True,
    message_editing=True,
    notifications=True,
)

# (update, acknowledge) -> None. `acknowledge` is set only for button presses.
UpdateHandler = Callable[[IncomingUpdate, Callable[[], Awaitable[None]] | None], Awaitable[None]]


def split_text(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Split at paragraph, line or word boundaries so no part exceeds Discord's limit."""
    parts: list[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = max(window.rfind("\n\n"), window.rfind("\n"))
        if cut <= 0:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip("\n ")
    parts.append(rest)
    return [part for part in parts if part] or [""]


def button_rows(buttons: list[list[dict[str, str]]] | None) -> list[list[dict[str, str]]]:
    """Re-chunk application rows into Discord's at most 5 buttons per row and 5 rows."""
    rows: list[list[dict[str, str]]] = []
    for row in buttons or []:
        for start in range(0, len(row), BUTTONS_PER_ROW):
            rows.append(row[start:start + BUTTONS_PER_ROW])
    if len(rows) > BUTTON_ROWS:
        raise ValueError("Discord messages carry at most 25 buttons in 5 rows")
    for row in rows:
        for button in row:
            if not 0 < len(button["callback_data"]) <= CUSTOM_ID_LIMIT:
                raise ValueError("Button data does not fit a Discord custom_id")
    return rows


def _view(buttons: list[list[dict[str, str]]] | None) -> discord.ui.View | None:
    rows = button_rows(buttons)
    if not rows:
        return None
    # Presses are decoded from on_interaction, not dispatched to this View; a short timeout lets
    # discord.py drop it from its view store instead of keeping one per message forever.
    view = discord.ui.View(timeout=1)
    for index, row in enumerate(rows):
        for button in row:
            view.add_item(discord.ui.Button(
                label=button["text"][:LABEL_LIMIT],
                custom_id=button["callback_data"],
                style=discord.ButtonStyle.secondary,
                row=index,
            ))
    return view


def decode_message(message) -> IncomingUpdate | None:
    """A DM from a person; guild messages, bots (including Amigo itself) and non-text ignored."""
    if getattr(message, "guild", None) is not None or getattr(message.author, "bot", False):
        return None
    if not isinstance(message.content, str) or not message.content:
        return None
    return IncomingUpdate(
        update_id=message.id,
        kind="message",
        chat_id=str(message.author.id),
        conversation=None,
        text=message.content,
        message_id=message.id,
    )


def decode_interaction(interaction) -> IncomingUpdate | None:
    """A button press on one of Amigo's DM messages."""
    if interaction.type != discord.InteractionType.component:
        return None
    if getattr(interaction, "guild_id", None) is not None or interaction.message is None:
        return None
    data = interaction.data or {}
    custom_id = data.get("custom_id")
    if not isinstance(custom_id, str) or not custom_id:
        return None
    return IncomingUpdate(
        update_id=interaction.id,
        kind="callback_query",
        chat_id=str(interaction.user.id),
        conversation=None,
        message_id=interaction.message.id,
        data=custom_id,
        callback_id=str(interaction.id),
    )


class DiscordChannel:
    """Direct messages with one Discord bot; the recipient is the participant's Discord user id."""

    channel_id = "discord"
    display_name = "Discord"
    capabilities = _CAPABILITIES

    def __init__(self, store, *, token: str | None = None, client: discord.Client | None = None):
        self.store = store
        self._token = token
        self.on_update: UpdateHandler | None = None
        self._dm_channels: dict[str, object] = {}
        self._task: asyncio.Task | None = None
        self.client = client or self._build_client()

    def _build_client(self) -> discord.Client:
        intents = discord.Intents.none()
        intents.dm_messages = True  # DM content needs no privileged message-content intent.
        client = discord.Client(intents=intents, allowed_mentions=discord.AllowedMentions.none())

        @client.event
        async def on_message(message):
            await self._dispatch(decode_message(message), None)

        @client.event
        async def on_interaction(interaction):
            update = decode_interaction(interaction)

            async def acknowledge() -> None:
                if not interaction.response.is_done():
                    await interaction.response.defer()

            await self._dispatch(update, acknowledge if update else None)

        return client

    async def _dispatch(self, update, acknowledge) -> None:
        if update is None or self.on_update is None:
            return
        try:
            await self.on_update(update, acknowledge)
        except Exception:
            # One bad event must never stop the gateway loop.
            logger.exception("Discord update failed kind=%s", update.kind)

    async def start(self) -> None:
        """Log in (fails fast on a bad token), then keep the gateway connected in the background."""
        if self._token is None:
            from src.config import settings

            self._token = settings.discord_bot_token
        await self.client.login(self._token)
        self._task = asyncio.create_task(
            self.client.connect(reconnect=True), name="discord-gateway"
        )

    async def close(self) -> None:
        await self.client.close()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task

    async def _dm(self, chat_id: str | int):
        key = str(chat_id)
        channel = self._dm_channels.get(key)
        if channel is None:
            user = self.client.get_user(int(key)) or await self.client.fetch_user(int(key))
            channel = user.dm_channel or await user.create_dm()
            self._dm_channels[key] = channel
        return channel

    def _validate_conversation(self, chat_id, conversation) -> None:
        if conversation is not None and (
            conversation.channel != self.channel_id
            or str(conversation.endpoint.get("chat_id")) != str(chat_id)
        ):
            raise ValueError("Conversation does not belong to this Discord recipient")

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
        conversation: ConversationRef | None = None,
    ) -> int | None:
        """Send in parts of at most 2000 characters; buttons ride on the last part.

        Returns the last part's id, the one carrying the buttons, as delivery proof.
        """
        self._validate_conversation(chat_id, conversation)
        view = _view(buttons)
        channel = await self._dm(chat_id)
        parts = split_text(text)
        message = None
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            kwargs = {"allowed_mentions": discord.AllowedMentions.none()}
            if last and view is not None:
                kwargs["view"] = view
            message = await channel.send(part, **kwargs)
        return message.id if message is not None else None

    async def edit_message_buttons(
        self,
        chat_id: str | int,
        message_id: int,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
        conversation: ConversationRef | None = None,
    ) -> None:
        self._validate_conversation(chat_id, conversation)
        channel = await self._dm(chat_id)
        await channel.get_partial_message(int(message_id)).edit(view=_view(buttons))

    async def create_conversation(self, chat_id: str | int, name: str) -> ConversationRef:
        """A DM is one endpoint; Mode commands select the canonical Mode."""
        return ConversationRef(self.channel_id, {"chat_id": str(chat_id)})

    async def close_conversation(self, chat_id: str | int, conversation: ConversationRef) -> None:
        self._validate_conversation(chat_id, conversation)

    async def conversation_link(self, conversation: ConversationRef | None) -> str | None:
        return None

    @property
    def connect_link(self) -> str | None:
        """Where the dashboard sends a participant to add the bot before typing `/pair`."""
        from src.config import settings

        app_id = str(settings.discord_application_id).strip()
        return f"https://discord.com/oauth2/authorize?client_id={app_id}" if app_id else None

    async def recipient_for(self, user: dict) -> str | int | None:
        if not user.get("user_id"):
            return None
        return (await self.store.list_channel_identities(user["user_id"])).get(self.channel_id)

    async def recipient_matches(self, conversation: ConversationRef, recipient: str | int) -> bool:
        return conversation.channel == self.channel_id and str(
            conversation.endpoint.get("chat_id")
        ) == str(recipient)
