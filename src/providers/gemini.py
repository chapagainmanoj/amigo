"""Gemini Flash provider — primary LLM for Phase 1a."""

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)


class GeminiProvider:
    """Gemini Flash implementation of ModelProvider protocol."""

    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = model
        self.client = genai.Client(api_key=settings.google_api_key)

    async def generate(
        self,
        messages: list[dict[str, str]],
        system: str,
        *,
        response_schema: type | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any] | str:
        """Generate response via Gemini API.

        Uses structured output (JSON mode) when response_schema is provided.
        """
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
        )

        if response_schema is not None:
            config.response_mime_type = "application/json"
            config.response_schema = response_schema

        # Convert message history to Gemini format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            text = response.text
            if response_schema is not None:
                return json.loads(text)
            return text

        except Exception:
            logger.exception("Gemini API call failed")
            raise

    async def count_tokens(self, text: str) -> int:
        """Estimate token count. Rough approximation: 1 token ≈ 4 chars."""
        # TODO: Use Gemini's count_tokens API for precision when needed
        return len(text) // 4

    def get_usage(self, response: Any) -> dict:
        """Extract token usage from response for usage_events tracking."""
        usage = getattr(response, "usage_metadata", None)
        if usage:
            return {
                "input_tokens": usage.prompt_token_count,
                "output_tokens": usage.candidates_token_count,
            }
        return {"input_tokens": 0, "output_tokens": 0}
