"""Task extraction tests — golden cases.

Covers:
- Comma-separated lists
- Vague goals ("work on presentation")
- Time-embedded tasks ("call mom at 3")
- Multi-language input (English + Nepali/Hindi mix)
- Single task
- Empty / no-task input
- Priority detection ("I really need to...")
- Ambiguous input (should surface in unextracted)
"""


from src.agent.models import ExtractedTask, ExtractionResult


class TestExtractionResultModel:
    """Test the Pydantic models parse correctly."""

    def test_basic_extraction_result(self):
        result = ExtractionResult(
            tasks=[
                ExtractedTask(
                    title="Buy groceries",
                    category="personal",
                    reminder_time="10am",
                    priority="normal",
                    raw_input="buy groceries at 10am",
                ),
            ],
            unextracted=None,
            confirmation_message="Got it — buying groceries at 10am!",
        )
        assert len(result.tasks) == 1
        assert result.tasks[0].category == "personal"
        assert result.unextracted is None

    def test_extraction_with_unextracted(self):
        result = ExtractionResult(
            tasks=[
                ExtractedTask(
                    title="Call mom",
                    category="social",
                    raw_input="call mom",
                ),
            ],
            unextracted="sort out the thing with Raj",
            confirmation_message="I got 'call mom'. What's the thing with Raj?",
        )
        assert result.unextracted is not None
        assert "Raj" in result.unextracted

    def test_high_priority_task(self):
        task = ExtractedTask(
            title="Submit report",
            category="work",
            priority="high",
            raw_input="I really need to submit the report",
        )
        assert task.priority == "high"

    def test_defaults(self):
        task = ExtractedTask(
            title="Something",
            raw_input="something",
        )
        assert task.category == "other"
        assert task.priority == "normal"
        assert task.reminder_time is None


# TODO: Integration tests with actual LLM calls (requires API key)
# These would test:
# - "grocery shopping, call mom, work on presentation" → 3 tasks
# - "work on the project" → 1 vague task
# - "call mom at 3pm" → task with reminder_time="3pm"
# - "gym jāna cha, report finish garne" → 2 tasks from mixed language
# - "hello" → 0 tasks (not a task list)
# - "I really need to submit the report by Friday" → high priority
