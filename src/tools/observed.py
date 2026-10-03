"""Track dispatched Tools without retaining their arguments or results."""

from contextvars import ContextVar

from pydantic_ai.toolsets import WrapperToolset

executed_tools: ContextVar[list[str] | None] = ContextVar("executed_tools", default=None)


class ObservedToolset(WrapperToolset):
    """Mark execution before dispatch, including a Tool which later raises an error."""

    async def call_tool(self, name, tool_args, ctx, tool):
        names = executed_tools.get()
        if names is not None:
            names.append(name)
        return await self.wrapped.call_tool(name, tool_args, ctx, tool)
