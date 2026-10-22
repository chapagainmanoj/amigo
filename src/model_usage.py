"""Content-free accounting at the Gemini SDK dispatch boundary."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from google.genai import errors
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
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
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(destination, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, payload)
        finally:
            os.close(descriptor)
    except OSError:
        # Do not print paths/errors that could carry environment information.
        logger.warning("Gemini usage metadata could not be recorded")


class LoggedGoogleModel(GoogleModel):
    """Count SDK dispatches, including failures, rather than completed Turns.

    Payload construction happens before accounting: local validation errors are not
    requests. GoogleModel's response processing still owns framework token usage.
    """

    async def _generate_content(self, messages, stream, model_settings, model_request_parameters):
        contents, config = await self._build_content_and_config(
            messages, model_settings, model_request_parameters
        )
        dispatch = (
            self.client.aio.models.generate_content_stream
            if stream
            else self.client.aio.models.generate_content
        )
        response = None
        outcome = "error"
        try:
            response = await dispatch(model=self.model_name, contents=contents, config=config)
            outcome = "ok"
            return response
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except errors.APIError as error:
            if error.code >= 400:
                raise ModelHTTPError(
                    status_code=error.code, model_name=self.model_name, body=error.details
                ) from error
            raise ModelAPIError(model_name=self.model_name, message=str(error)) from error
        finally:
            usage = getattr(response, "usage_metadata", None)
            candidates = getattr(usage, "candidates_token_count", None)
            thoughts = getattr(usage, "thoughts_token_count", None)
            output_tokens = (
                None
                if candidates is None and thoughts is None
                else (candidates or 0) + (thoughts or 0)
            )
            await record_gemini_request(
                f"google:{self.model_name}",
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=output_tokens,
                outcome=outcome,
            )
