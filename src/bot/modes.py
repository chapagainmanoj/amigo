"""One application resolver for threaded conversations and explicit in-chat Mode commands."""

from dataclasses import dataclass

from src.agent.modes import ModeUnavailableError
from src.conversations import ModeConversationService
from src.tools.context import ToolContext
from src.wellbeing import reflect_safety_response


@dataclass
class PreparedModeTurn:
    context: ToolContext
    mode_id: str
    response: str | None = None


class ModeController:
    def __init__(self, store, channel, scheduler, session_mgr, runtime):
        self.store, self.channel, self.scheduler = store, channel, scheduler
        self.sessions, self.runtime = session_mgr, runtime
        self.conversations = ModeConversationService(store, channel)

    async def prepare(self, chat_id, user, text, update_id, conversation=None):
        user_id = user["user_id"]
        timezone = user.get("timezone") or "UTC"
        timeout = user.get("session_timeout_minutes", 120)
        addressed_mode = await self.conversations.select(user, conversation)
        control = None
        if addressed_mode is None:
            control, _ = await self.sessions.get_or_create_session(
                user_id, timeout, timezone=timezone
            )
            selected = await self.store.get_active_mode(user_id, control["session_id"])
        else:
            selected = addressed_mode
        parts = text.strip().split()
        command = parts[0] if parts else ""
        is_mode_command = command in {"/mode", "/daily"}
        context = ToolContext(
            store=self.store, scheduler=self.scheduler, channel=self.channel, user=user,
            session_id="", chat_id=chat_id, timezone=timezone, turn_id=str(update_id),
            conversation=conversation,
            entered_by="topic" if addressed_mode is not None else "command",
        )
        if command == "/mode" and len(parts) == 1:
            available = []
            for mode in await self.runtime.registry.live():
                if await self.runtime.entitlements.allows(context, mode):
                    available.append(f"/mode {mode.id} — {mode.purpose}")
            return PreparedModeTurn(context, selected, "Choose a Mode:\n" + "\n".join(available))
        if is_mode_command:
            if (command == "/daily" and len(parts) != 1) or (
                command == "/mode" and len(parts) != 2
            ):
                return PreparedModeTurn(context, selected, "Use /mode, /mode <id>, or /daily.")
            selected = "daily" if command == "/daily" else parts[1]
        safety_reply = await reflect_safety_response(selected, text)
        if safety_reply is not None:
            return PreparedModeTurn(context, selected, safety_reply)
        try:
            mode = await self.runtime.resolve(context, selected)
        except ModeUnavailableError as error:
            if not is_mode_command and control is not None and selected != "daily":
                await self.store.set_active_mode(user_id, control["session_id"], "daily")
            return PreparedModeTurn(context, selected or "daily", error.participant_message)
        except Exception:
            from src.agent.runtime import FAILURE_REPLY

            return PreparedModeTurn(context, selected or "daily", FAILURE_REPLY)
        selected = mode.id
        session, _ = await self.sessions.get_or_create_session(
            user_id, timeout, timezone=timezone, mode_id=selected
        )
        context.session_id = session["session_id"]
        # 016's trusted source check is kept in sync with the fixed Mode-scoped Session.
        result = {"status": "set"}
        if (session.get("active_mode_id") or "daily") != selected:
            result = await self.store.set_active_mode(
                user_id, session["session_id"], selected, grant_required=mode.entitlement == "grant"
            )
        if result["status"] != "set":
            return PreparedModeTurn(
                context, selected, f"{mode.name} isn't available on your account."
            )
        if is_mode_command:
            if control is None:
                control, _ = await self.sessions.get_or_create_session(user_id, timezone=timezone)
            if (control.get("active_mode_id") or "daily") != selected:
                await self.store.set_active_mode(
                    user_id, control["session_id"], selected,
                    grant_required=mode.entitlement == "grant",
                )
            context.conversation = await self.conversations.ensure(user, selected, chat_id=chat_id)
            return PreparedModeTurn(
                context, selected, f"{mode.name}: {mode.purpose}\n{mode.limits}"
            )
        if context.conversation is None:
            context.conversation = await self.conversations.ensure(user, selected, chat_id=chat_id)
        return PreparedModeTurn(context, selected)
