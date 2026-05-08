"""Pydantic models for structured LLM output."""

from pydantic import BaseModel, Field


class ExtractedTask(BaseModel):
    """A single task extracted from user's natural language input."""

    title: str = Field(description="Clear, actionable task title")
    category: str = Field(
        default="other",
        description="Task category: health, work, personal, social, or other",
    )
    reminder_time: str | None = Field(
        default=None,
        description=(
            'When to remind, as spoken by user: "3pm", "after lunch", etc. '
            "None if not specified."
        ),
    )
    priority: str = Field(
        default="normal",
        description=(
            'Priority level: "high" if user expressed urgency, else "normal"'
        ),
    )
    raw_input: str = Field(
        description="The original phrase from user input that generated this task"
    )


class ExtractionResult(BaseModel):
    """Result of task extraction from a user message."""

    tasks: list[ExtractedTask] = Field(description="List of extracted tasks")
    unextracted: str | None = Field(
        default=None,
        description=(
            "Any input the model couldn't confidently parse into a task. "
            "Surface back to user for clarification."
        ),
    )
    confirmation_message: str = Field(
        description="Natural language confirmation of what was extracted, ready to send to user"
    )


class TaskStatusUpdate(BaseModel):
    """When user indicates a task is done/skipped via text (not inline keyboard)."""

    task_title_match: str = Field(
        description="The task title this update refers to (fuzzy match OK)"
    )
    new_status: str = Field(
        description='New status: "done", "skipped", "deferred", or "none"'
    )
    response_message: str = Field(description="Brief confirmation to send back")


class ReminderTimeResolution(BaseModel):
    """Resolve natural language time to HH:MM format."""

    original: str = Field(description='The original time expression: "3pm", "after lunch"')
    resolved_time: str = Field(
        description='Resolved to 24h format HH:MM, e.g. "15:00". Use best judgment for vague times.'
    )
    confidence: str = Field(
        default="high",
        description='"high" for exact times ("3pm"), "medium" for relative ("after lunch")',
    )
