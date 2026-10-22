"""Telegram transport: all Bot API, topic identifiers and update decoding stay here."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Literal

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from src.channels.base import ChannelCapabilities, ConversationRef, ConversationUnavailableError
from src.config import settings

logger = logging.getLogger(__name__)
_CAPABILITIES = ChannelCapabilities(
    actions=True,
    delivery_acknowledgement=True,
    message_editing=True,
    deep_links=True,
    notifications=True,
)


@dataclass(frozen=True)
class IncomingUpdate:
    update_id: int
    kind: Literal["message", "callback_query"]
    chat_id: int
    conversation: ConversationRef | None
    text: str | None = None
    message_id: int | None = None
    data: str | None = None
    callback_id: str | None = None


class TelegramChannel:
    """Topics are a transport capability; the application owns their Mode assignments."""

    channel_id = "telegram"
    capabilities = _CAPABILITIES
    default_conversation_resolver: (
        Callable[[str | int], Awaitable[ConversationRef | None]] | None
    ) = None

    def __init__(self, *, token: str | None = None):
        self._token = token
        self._bot: Bot | None = None

    @property
    def bot(self) -> Bot:
        if getattr(self, "_bot", None) is None:
            self._bot = Bot(token=getattr(self, "_token", None) or settings.telegram_bot_token)
        return self._bot

    @bot.setter
    def bot(self, value: Bot) -> None:
        self._bot = value

    async def initialize(self, *, production: bool = False) -> str | None:
        try:
            info = await self.bot.get_me()
        except Exception as error:
            self.capabilities = replace(_CAPABILITIES, threads=False)
            self._username = None
            if production:
                raise RuntimeError("Telegram capability check failed") from None
            logger.warning(
                "Telegram capability check failed; in-chat Mode commands remain available (%s)",
                type(error).__name__,
            )
            return None
        topics = getattr(info, "has_topics_enabled", False) is True
        user_topics = getattr(info, "allows_users_to_create_topics", None)
        self.capabilities = replace(_CAPABILITIES, threads=topics)
        self._username = getattr(info, "username", None)
        logger.info("telegram_topics enabled=%s user_created=%s", topics, user_topics)
        if not topics:
            logger.warning("Telegram topics disabled; using in-chat Mode commands")
        elif user_topics is not False:
            if production and user_topics is True:
                raise RuntimeError("Telegram Threaded Mode requires user-created threads off")
            logger.warning("Telegram user-created threads should be disabled")
        return getattr(info, "username", None)

    async def create_conversation(self, chat_id: str | int, name: str) -> ConversationRef:
        if not self.capabilities.threads:
            return ConversationRef(self.channel_id, {"chat_id": chat_id})
        topic = await self.bot.create_forum_topic(chat_id=chat_id, name=name)
        thread_id = topic.message_thread_id
        if type(thread_id) is not int or thread_id <= 0:
            raise ValueError("Telegram returned an invalid conversation")
        return ConversationRef(self.channel_id, {"chat_id": chat_id, "thread_id": thread_id})

    async def close_conversation(self, chat_id: str | int, conversation: ConversationRef) -> None:
        thread_id = self._thread_for(chat_id, conversation)
        if thread_id is not None:
            await self.bot.close_forum_topic(chat_id=chat_id, message_thread_id=thread_id)

    def _thread_for(self, chat_id, conversation):
        if conversation.channel != self.channel_id or str(
            conversation.endpoint.get("chat_id")
        ) != str(chat_id):
            raise ValueError("Conversation does not match the channel endpoint")
        if set(conversation.endpoint) - {"chat_id", "thread_id"}:
            raise ValueError("Invalid Telegram conversation endpoint")
        thread_id = conversation.endpoint.get("thread_id")
        if thread_id is not None and (type(thread_id) is not int or thread_id <= 0):
            raise ValueError("Invalid Telegram conversation endpoint")
        return thread_id

    async def _address(self, chat_id, conversation):
        if conversation is not None:
            thread_id = self._thread_for(chat_id, conversation)
            if thread_id is not None or not self.capabilities.threads:
                return conversation
            raise ValueError("Threaded Telegram delivery requires a conversation thread")
        if not self.capabilities.threads:
            return None
        resolver = self.default_conversation_resolver
        if resolver is not None:
            resolved = await resolver(chat_id)
            if resolved is not None:
                if self._thread_for(chat_id, resolved) is None:
                    raise ValueError("Default conversation requires a thread")
                return resolved
        # Unpaired recipients have no canonical conversation. Do not create provider resources
        # for them or send without a thread (which would create one implicitly).
        return None

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
        conversation: ConversationRef | None = None,
    ) -> int | None:
        conversation = await self._address(chat_id, conversation)
        if self.capabilities.threads and conversation is None:
            logger.warning("Telegram reply omitted: no authorized conversation")
            return None
        kwargs = {"chat_id": chat_id, "text": text, "reply_markup": _markup(buttons)}
        if conversation is not None:
            thread_id = self._thread_for(chat_id, conversation)
            if thread_id is not None:
                kwargs["message_thread_id"] = thread_id
        try:
            message = await self.bot.send_message(**kwargs)
        except BadRequest as error:
            if conversation is not None and "message thread not found" in str(error).lower():
                raise ConversationUnavailableError(conversation) from None
            raise
        return message.message_id

    async def edit_message_buttons(
        self,
        chat_id: str | int,
        message_id: int,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
        conversation: ConversationRef | None = None,
    ) -> None:
        if conversation is not None:
            self._thread_for(chat_id, conversation)
        # Editing is addressed by the existing message ID; Bot API has no thread parameter.
        await self.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=_markup(buttons),
        )

    async def conversation_from_update(self, data: dict) -> ConversationRef | None:
        query = data.get("callback_query")
        message = data.get("message") or (query.get("message") if isinstance(query, dict) else None)
        if not isinstance(message, dict) or message.get("date") == 0:
            return None
        chat = message.get("chat")
        chat_id = chat.get("id") if isinstance(chat, dict) else None
        thread_id = message.get("message_thread_id")
        if type(chat_id) is not int or type(thread_id) is not int or thread_id <= 0:
            return None
        return ConversationRef(self.channel_id, {"chat_id": chat_id, "thread_id": thread_id})

    async def decode_update(self, data: dict) -> IncomingUpdate | None:
        if not isinstance(data, dict) or type(data.get("update_id")) is not int:
            return None
        query = data.get("callback_query")
        message = query.get("message") if isinstance(query, dict) else data.get("message")
        if not isinstance(message, dict) or message.get("date") == 0:
            return None  # CallbackQuery may contain an inaccessible message.
        chat = message.get("chat")
        chat_id = chat.get("id") if isinstance(chat, dict) else None
        if type(chat_id) is not int:
            return None
        conversation = await self.conversation_from_update(data)
        if isinstance(query, dict):
            if not isinstance(query.get("data"), str) or type(message.get("message_id")) is not int:
                return None
            if not isinstance(query.get("id"), str):
                return None
            return IncomingUpdate(
                data["update_id"],
                "callback_query",
                chat_id,
                conversation,
                message_id=message["message_id"],
                data=query["data"],
                callback_id=query["id"],
            )
        if isinstance(message.get("text"), str):
            return IncomingUpdate(
                data["update_id"], "message", chat_id, conversation, text=message["text"]
            )
        return None

    async def conversation_link(self, conversation: ConversationRef | None) -> str | None:
        if conversation is not None and conversation.channel != self.channel_id:
            return None
        username = getattr(self, "_username", None)
        return f"https://t.me/{username}" if username else None

    async def recipient_matches(self, conversation: ConversationRef, recipient: str | int) -> bool:
        return conversation.channel == self.channel_id and str(
            conversation.endpoint.get("chat_id")
        ) == str(recipient)

    async def recipient_for(self, user: dict) -> str | int | None:
        return user.get("telegram_chat_id")

    async def acknowledge_callback(self, callback_id: str) -> None:
        await self.bot.answer_callback_query(callback_query_id=callback_id)


def _markup(buttons):
    if not buttons:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text=button["text"], callback_data=button["callback_data"])
                for button in row
            ]
            for row in buttons
        ]
    )
