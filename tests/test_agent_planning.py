"""Agent planning tests."""

from src.agent.amigo import AmigoAgent
from src.agent.models import AgentDecision
from tests.fakes import FakeModel, FakeStore


async def test_plan_task_list_with_reminder_returns_tool_calls():
    store = FakeStore()
    model = FakeModel()
    model.responses["ExtractionResult"] = {
        "tasks": [
            {
                "title": "Call mom",
                "category": "social",
                "reminder_time": "3pm",
                "priority": "normal",
                "raw_input": "call mom at 3pm",
            }
        ],
        "unextracted": None,
        "confirmation_message": "Got it — call mom at 3pm.",
    }
    model.responses["ReminderTimeResolution"] = {
        "original": "3pm",
        "resolved_time": "15:00",
        "confidence": "high",
    }
    agent = AmigoAgent(model, store)

    decision = await agent.plan_message(
        {"user_id": "user-1"},
        "today I need to call mom at 3pm",
        pending_tasks=[],
        timezone="Asia/Kathmandu",
    )

    assert isinstance(decision, AgentDecision)
    assert decision.message_type == "task_list"
    assert [call.name for call in decision.tool_calls] == [
        "create_task",
        "schedule_reminder",
    ]
    assert decision.tool_calls[0].arguments["task_ref"] == "task_0"
    assert decision.tool_calls[1].arguments["task_ref"] == "task_0"
    assert decision.tool_calls[1].arguments["resolved_time"] == "15:00"


async def test_plan_plain_chat_returns_no_tool_calls():
    store = FakeStore()
    model = FakeModel()
    model.responses["ExtractionResult"] = {
        "tasks": [],
        "unextracted": None,
        "confirmation_message": "",
    }
    agent = AmigoAgent(model, store)

    decision = await agent.plan_message(
        {"user_id": "user-1"},
        "hello amigo",
        pending_tasks=[],
        timezone="Asia/Kathmandu",
    )

    assert decision.message_type == "chat"
    assert decision.tool_calls == []


async def test_plan_status_update_returns_update_tool_call():
    store = FakeStore()
    model = FakeModel()
    model.responses["TaskStatusUpdate"] = {
        "task_title_match": "slides",
        "new_status": "done",
        "response_message": "Nice — slides done!",
    }
    agent = AmigoAgent(model, store)

    decision = await agent.plan_message(
        {"user_id": "user-1"},
        "finished the slides",
        pending_tasks=[
            {"task_id": "task-1", "title": "finish slides", "status": "pending"}
        ],
        timezone="Asia/Kathmandu",
    )

    assert decision.message_type == "status_update"
    assert decision.reply == "Nice — slides done!"
    assert len(decision.tool_calls) == 1
    assert decision.tool_calls[0].name == "update_task_status"
    assert decision.tool_calls[0].arguments == {"task_id": "task-1", "status": "done"}
