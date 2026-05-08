"""ModelProvider protocol — swap LLM backends without touching agent code."""

from typing import Any, Protocol


class ModelProvider(Protocol):
    """Abstract interface for LLM providers.

    Agent code calls generate() without knowing if it's Gemini, Claude, or local.
    """

    async def generate(
        self,
        messages: list[dict[str, str]],
        system: str,
        *,
        response_schema: type | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any] | str:
        """Generate a response from the LLM.

        Args:
            messages: Conversation history [{"role": "user"|"assistant", "content": "..."}]
            system: System prompt
            response_schema: If provided, return structured JSON matching this Pydantic model
            temperature: Sampling temperature

        Returns:
            Structured dict if response_schema provided, else raw string.
        """
        ...

    async def count_tokens(self, text: str) -> int:
        """Estimate token count for context budget management."""
        ...
