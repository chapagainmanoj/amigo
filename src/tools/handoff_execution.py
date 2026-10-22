"""Persist public model response steps before dispatching idempotent handoff Tools."""

from pydantic import TypeAdapter
from pydantic_ai.messages import ModelResponse, ThinkingPart, ToolCallPart
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.usage import RequestUsage


class DurableHandoffModel(WrapperModel):
    def __init__(self, wrapped, store, user_id, handoff, context=None):
        super().__init__(wrapped)
        self.store, self.user_id, self.handoff = store, user_id, handoff
        self.plan = list(handoff.get("execution_plan") or [])
        self.index = 0
        self.context = context

    async def request(self, messages, model_settings, model_request_parameters):
        adapter = TypeAdapter(ModelResponse)
        if self.index < len(self.plan):
            response = adapter.validate_python(self.plan[self.index]["response"])
            response.usage = RequestUsage()  # Replaying a retained step makes no provider request.
        else:
            settings = dict(model_settings or {})
            # Opaque provider signatures are retained; private reasoning text is not retained.
            settings["google_thinking_config"] = {"include_thoughts": False}
            response = await self.wrapped.request(messages, settings, model_request_parameters)
            if any(isinstance(part, ThinkingPart) and part.content for part in response.parts):
                raise ValueError("Handoff response contains unsupported private reasoning")
            step = {"response": adapter.dump_python(response, mode="json")}
            if self.context is not None:
                step["execution_context"] = {
                    "timezone": self.context.timezone,
                    "wake_time": self.context.user.get("wake_time", "07:30"),
                    "sleep_time": self.context.user.get("sleep_time", "23:00"),
                }
                targets = {}
                for part in response.parts:
                    if isinstance(part, ToolCallPart) and part.tool_name == "cancel_reminders":
                        task_id = part.args_as_dict().get("task_id")
                        if isinstance(task_id, str):
                            rows = await self.store.get_pending_reminders(self.user_id)
                            targets[task_id] = [
                                row["reminder_id"] for row in rows if row["task_id"] == task_id
                            ]
                step["cancel_targets"] = targets
            self.plan.append(step)
        # Fence even replayed steps before a Tool can commit. The plan is append-only in SQL.
        if not await self.store.save_handoff_execution_plan(
            self.user_id, self.handoff["handoff_id"], self.handoff["execution_claim_token"],
            self.plan,
        ):
            raise RuntimeError("Handoff execution claim unavailable")
        if self.context is not None:
            self.context.handoff_cancel_targets = self.plan[self.index].get("cancel_targets", {})
        self.index += 1
        return response

