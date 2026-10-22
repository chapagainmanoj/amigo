"""Optional, unregistered candidate Toolset. No Tool can confirm or silently save Memory."""

from pydantic_ai import FunctionToolset, RunContext

from src.memory_service import MemoryController, memory_now
from src.tools.context import ToolContext

MEMORY_CANDIDATES: FunctionToolset[ToolContext] = FunctionToolset(max_retries=0)


@MEMORY_CANDIDATES.tool
async def propose_memory(ctx: RunContext[ToolContext], category: str, text: str) -> str:
    """Offer an exact eligible Memory preview; participant confirmation is always required.

    Never propose prohibited sensitive content or infer consent from silence or repeated behavior.
    This Tool has no confirmation capability and cannot enable Memory or write a saved item.
    """
    context = ctx.deps
    service = getattr(context, "memory_service", None)
    if service is None:
        return "Memory saving is unavailable pending privacy and eligibility review."
    messages = await context.store.get_session_messages(context.session_id)
    source = next(
        (
            row
            for row in reversed(messages)
            if row["role"] == "user" and row["user_id"] == context.user["user_id"]
        ),
        None,
    )
    if source is None:
        return "Memory needs an owned source Message and explicit confirmation."
    payload = dict(
        category=category,
        text=text,
        source_mode_id=context.mode_id,
        source_channel=context.channel.channel_id,
        source_message_id=source["message_id"],
        source_date=memory_now(context.clock).date().isoformat(),
        creation_path="amigo_proposed",
        scopes=[context.mode_id],
        valid_until=None,
    )
    try:
        preview = await service.propose(context.user["user_id"], payload)
        from src.config import settings

        await MemoryController(
            service, context.channel, settings.dashboard_url + "/#memory"
        ).show_preview(
            context.user,
            context.chat_id,
            preview,
            context.conversation,
        )
    except ValueError:
        return "Memory cannot be saved or proposed right now. No item was saved."
    return "An exact Memory preview was shown. Nothing is saved unless the participant confirms."
