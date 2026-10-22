"""Local development/eval accounting through public Gemini request results."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import httpx
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models.google import GoogleModel

from src.utils import utc_now

DEFAULT_USAGE_PATH = Path(__file__).resolve().parents[1] / ".scratch/gemini-usage.jsonl"
logger = logging.getLogger(__name__)


async def record_gemini_request(
    model_id: str,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    outcome: str = "ok",
    path: Path | None = None,
) -> None:
    """Append one dispatched request, retaining no participant or exception content.

    Unknown token counts remain null rather than claiming failed requests were free.
    One append-only write keeps simultaneous local callers from interleaving records.
    """
    if outcome not in {"ok", "error", "cancelled"}:
        raise ValueError("Unknown Gemini request outcome")
    record = {
        "at": utc_now().isoformat(),
        "model_id": model_id,
        "requests": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "outcome": outcome,
    }
    destination = path if path is not None else DEFAULT_USAGE_PATH
    payload = (json.dumps(record, separators=(",", ":")) + "\n").encode()
    await asyncio.to_thread(_append_usage, destination, payload)


def _append_usage(destination: Path, payload: bytes) -> None:
    """All filesystem work stays off the event loop, including directory creation."""
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(destination, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, payload)
        finally:
            os.close(descriptor)
    except OSError:
        logger.warning("Gemini usage metadata could not be recorded")


class LoggedGoogleModel(GoogleModel):
    """Development/eval-only non-streaming request accounting.

    Read the public ModelResponse usage, which already includes framework token accounting.
    Failed provider requests have unknown token counts. Local validation errors do not count
    as requests. Production runtime builds plain GoogleModel; the eval runner opts in explicitly.
    """

    async def request(self, messages, model_settings, model_request_parameters):
        try:
            response = await super().request(messages, model_settings, model_request_parameters)
        except asyncio.CancelledError:
            await record_gemini_request(f"google:{self.model_name}", outcome="cancelled")
            raise
        except (ModelAPIError, ModelHTTPError, UnexpectedModelBehavior, httpx.HTTPError):
            await record_gemini_request(f"google:{self.model_name}", outcome="error")
            raise
        await record_gemini_request(
            f"google:{self.model_name}",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return response
