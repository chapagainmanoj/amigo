"""Core Amigo agent — orchestrates conversation, task extraction, and memory."""

import json
import logging

from src.agent.models import ExtractionResult, ReminderTimeResolution, TaskStatusUpdate
from src.agent.prompts import (
    REMINDER_TIME_PROMPT,
    TASK_EXTRACTION_PROMPT,
    TASK_STATUS_PROMPT,
    build_system_prompt,
)
from src.memory.context import ContextBuilder
from src.memory.store import MemoryStore
from src.providers.base import ModelProvider

logger = logging.getLogger(__name__)


class AmigoAgent:
    """The core agent. Channel-agnostic, model-agnostic.

    Handles:
    - General conversation (system prompt + context)
    - Task extraction (structured output)
    - Reminder time resolution
    - Task status updates via conversation
    """

    def __init__(self, model: ModelProvider, store: MemoryStore):
        self.model = model
        self.store = store
        self.context_builder = ContextBuilder(store)

    async def chat(self, user: dict, session_id: str, user_message: str) -> str:
        """Main conversation handler. Returns Amigo's response.

        Flow:
        1. Store user message
        2. Build context (profile + yesterday + today + session)
        3. Call LLM
        4. Store assistant response
        5. Return response text
        """
        user_id = user["user_id"]
        name = user.get("name") or "friend"

        # Store user message
        await self.store.add_message(session_id, user_id, "user", user_message)

        # Build context
        messages = await self.context_builder.build(user, session_id)

        # Generate response (1 retry on failure)
        system = build_system_prompt(name)
        response = await self._generate_with_retry(messages, system)

        # Store assistant response
        await self.store.add_message(session_id, user_id, "assistant", response)

        return response

    async def morning_planning(self, user: dict, session_id: str, user_message: str) -> str:
        """Deterministic morning planning — surfaces yesterday's tasks, asks about today.

        Uses a tighter system prompt that forces the model to:
        1. Mention specific incomplete tasks from yesterday
        2. Ask what's planned for today
        3. Acknowledge whatever the user said in their first message

        Stores both user message and response in session for context coherence.
        """
        user_id = user["user_id"]
        name = user.get("name") or "friend"
        tz = user.get("timezone") or "UTC"

        # Store user message
        await self.store.add_message(session_id, user_id, "user", user_message)

        # Get yesterday's pending tasks
        yesterday_tasks = await self.store.get_yesterday_pending(user_id, tz)
        today_tasks = await self.store.get_today_tasks(user_id, tz)

        # Build a focused morning prompt
        yesterday_block = ""
        if yesterday_tasks:
            task_names = ", ".join(f"'{t['title']}'" for t in yesterday_tasks)
            yesterday_block = (
                f"\nYesterday's unfinished tasks: {task_names}. "
                "Ask about each one — curious, not judgmental. "
                "For each, ask: still on the list or should we drop it?"
            )

        today_block = ""
        if today_tasks:
            task_names = ", ".join(f"'{t['title']}'" for t in today_tasks)
            today_block = f"\nAlready on today's list: {task_names}."

        morning_system = f"""{build_system_prompt(name)}

<morning_planning>
This is {name}'s first message of the day. Write a morning greeting that:
1. Greets {name} naturally{yesterday_block}
2. Acknowledges what {name} just said in their message{today_block}
3. If they haven't mentioned plans yet, ask what's on the plate for today

Keep it to 2-4 sentences. Don't list every task mechanically — weave them into conversation.
</morning_planning>"""

        messages = await self.context_builder.build(user, session_id)
        response = await self._generate_with_retry(messages, morning_system)

        await self.store.add_message(session_id, user_id, "assistant", response)
        return response

    async def extract_tasks(self, user_message: str) -> ExtractionResult:
        """Extract structured tasks from user's natural language input.

        Returns ExtractionResult with tasks, unextracted text, and confirmation message.
        """
        messages = [{"role": "user", "content": user_message}]
        result = await self.model.generate(
            messages,
            TASK_EXTRACTION_PROMPT,
            response_schema=ExtractionResult,
            temperature=0.3,  # Lower temp for structured extraction
        )

        if isinstance(result, dict):
            return ExtractionResult(**result)
        # Fallback: try parsing string response as JSON
        return ExtractionResult(**json.loads(result))

    async def resolve_reminder_time(
        self, time_expression: str, timezone: str = "Asia/Kathmandu"
    ) -> ReminderTimeResolution:
        """Convert natural language time to HH:MM format."""
        prompt = REMINDER_TIME_PROMPT.format(timezone=timezone)
        messages = [{"role": "user", "content": f"Time to resolve: {time_expression}"}]

        result = await self.model.generate(
            messages,
            prompt,
            response_schema=ReminderTimeResolution,
            temperature=0.1,  # Very low temp — we want deterministic time resolution
        )

        if isinstance(result, dict):
            return ReminderTimeResolution(**result)
        return ReminderTimeResolution(**json.loads(result))

    async def detect_status_update(
        self, user_message: str, pending_tasks: list[dict]
    ) -> TaskStatusUpdate | None:
        """Detect if user message is a task status update.

        Args:
            user_message: The user's text (e.g., "done with slides")
            pending_tasks: Today's pending/deferred tasks for matching

        Returns:
            TaskStatusUpdate if match found, None if message isn't a status update.
        """
        if not pending_tasks:
            return None

        task_list = "\n".join(
            f"- {t['title']} (status: {t['status']})" for t in pending_tasks
        )
        prompt = TASK_STATUS_PROMPT.format(task_list=task_list)
        messages = [{"role": "user", "content": user_message}]

        try:
            result = await self.model.generate(
                messages,
                prompt,
                response_schema=TaskStatusUpdate,
                temperature=0.1,
            )
            if isinstance(result, dict):
                update = TaskStatusUpdate(**result)
            else:
                update = TaskStatusUpdate(**json.loads(result))

            # "none" means the LLM decided this isn't a status update
            if update.new_status == "none":
                return None
            return update
        except Exception:
            logger.debug("Status update detection failed, treating as regular message")
            return None

    async def _generate_with_retry(
        self, messages: list[dict], system: str, max_retries: int = 1
    ) -> str:
        """Generate with 1 silent retry. On final failure, return honest error."""
        for attempt in range(max_retries + 1):
            try:
                result = await self.model.generate(messages, system)
                if isinstance(result, str):
                    return result
                return str(result)
            except Exception:
                if attempt < max_retries:
                    logger.warning("LLM call failed (attempt %d), retrying...", attempt + 1)
                    continue
                logger.exception("LLM call failed after %d attempts", max_retries + 1)
                return "Sorry, having trouble thinking right now. Try again in a minute? 🙏"
