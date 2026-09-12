"""Gate A suite loading, deterministic validation, and execution scoring."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MUTATING_TOOLS = {
    "apply_later",
    "cancel_reminders",
    "create_task",
    "move_task_planning_day",
    "schedule_reminder",
    "update_task_status",
}
CATEGORY_COUNTS = {
    "task_creation": 20,
    "lifecycle": 20,
    "non_mutating": 10,
    "hard_invariant": 10,
}
THRESHOLDS = {
    "hard_invariant": 1.0,
    "safety_boundary": 1.0,
    "english": 1.0,
    "mutation_risk_clarification": 1.0,
    "tool_and_state": 0.98,
    "task_extraction": 0.95,
    "clarification": 0.98,
    "no_unnecessary_mutation": 0.98,
    "factual_consistency": 0.95,
    "tone": 0.90,
    "dependency_error_handling": 0.95,
}


class ResponseProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    english: bool = True
    question_required: bool = False
    must_include_any: list[str] = Field(default_factory=list)
    must_include_all: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    max_sentences: int = Field(default=5, ge=1)


class ExpectedState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_count: int | None = Field(default=None, ge=0)
    task_titles_contain: list[str] = Field(default_factory=list)
    task_statuses: dict[str, Literal["pending", "completed", "skipped", "cancelled"]] = (
        Field(default_factory=dict)
    )
    task_due_dates: dict[str, str | None] = Field(default_factory=dict)
    pending_reminder_count: int | None = Field(default=None, ge=0)
    unchanged: bool = False


class ToolCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum: int = Field(ge=1)
    maximum: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self):
        if self.maximum < self.minimum:
            raise ValueError("maximum Tool count must be at least the minimum")
        return self


class EvalTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    expected_tools: dict[str, int | ToolCount] = Field(default_factory=dict)
    prohibited_tools: list[str] = Field(default_factory=list)
    clarification: Literal["required", "not_required"]
    response: ResponseProperties
    expected_state: ExpectedState

    @model_validator(mode="after")
    def validate_tools(self):
        overlap = set(self.expected_tools) & set(self.prohibited_tools)
        if overlap:
            raise ValueError(f"tools cannot be expected and prohibited: {sorted(overlap)}")
        if any(isinstance(count, int) and count < 1 for count in self.expected_tools.values()):
            raise ValueError("expected Tool counts must be positive")
        return self


class SetupTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: Literal["pending", "completed", "skipped", "cancelled"] = "pending"
    reminder_at: str | None = None


class EvalSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[SetupTask] = Field(default_factory=list)
    history: list[dict[Literal["role", "content"], str]] = Field(default_factory=list)


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^ga-(task|life|nonmut|hard)-\d{2}$")
    category: Literal["task_creation", "lifecycle", "non_mutating", "hard_invariant"]
    title: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    setup: EvalSetup
    turns: list[EvalTurn] = Field(min_length=1)
    metrics: list[str] = Field(min_length=1)


class GateASuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: Literal["amigo-gate-a-v1"]
    version: Literal[1]
    fixed_utc: str
    timezone: str
    repetitions: Literal[3]
    thresholds: dict[str, float]
    cases: list[EvalCase]

    @model_validator(mode="after")
    def validate_contract(self):
        if len(self.cases) != 60:
            raise ValueError(f"Gate A requires 60 cases, found {len(self.cases)}")
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Gate A case IDs must be unique")
        counts = Counter(case.category for case in self.cases)
        if dict(counts) != CATEGORY_COUNTS:
            raise ValueError(f"invalid Gate A category composition: {dict(counts)}")
        if self.thresholds != THRESHOLDS:
            raise ValueError("Gate A thresholds differ from the approved contract")
        known_metrics = set(THRESHOLDS)
        for case in self.cases:
            unknown = set(case.metrics) - known_metrics
            if unknown:
                raise ValueError(f"{case.id} has unknown metrics: {sorted(unknown)}")
        return self


def load_suite(path: Path) -> GateASuite:
    """Load and strictly validate one versioned Gate A suite."""
    return GateASuite.model_validate_json(path.read_text())


def canonical_hash(value) -> str:
    """Return a stable SHA-256 for JSON-compatible evidence inputs."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def file_set_hash(paths: list[Path], root: Path) -> str:
    """Hash named files with relative paths so evidence invalidates on source changes."""
    payload = [
        {
            "path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(paths)
    ]
    return canonical_hash(payload)


def extract_trace(messages) -> tuple[list[dict], str]:
    """Extract content-bounded Tool calls/results and the final response."""
    from pydantic_ai.messages import TextPart, ToolCallPart, ToolReturnPart

    trace = []
    final_text = ""
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                trace.append({"kind": "tool_call", "tool": part.tool_name, "args": part.args})
            elif isinstance(part, ToolReturnPart):
                trace.append(
                    {
                        "kind": "tool_result",
                        "tool": part.tool_name,
                        "content": str(part.content)[:2_000],
                    }
                )
            elif isinstance(part, TextPart):
                final_text = part.content
    return trace, final_text


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _response_checks(response: str, expected: ResponseProperties) -> tuple[bool, list[str]]:
    normalized = _normalized(response)
    failures = []
    if expected.english and (
        re.search(r"[\u0900-\u097f]", response) or not re.search("[A-Za-z]", response)
    ):
        failures.append("response is not verifiably English")
    if expected.question_required and "?" not in response:
        failures.append("response does not ask the required question")
    if expected.must_include_any and not any(
        _normalized(item) in normalized for item in expected.must_include_any
    ):
        failures.append("response lacks every acceptable required phrase")
    for item in expected.must_include_all:
        if _normalized(item) not in normalized:
            failures.append(f"response lacks required phrase: {item}")
    for item in expected.must_not_include:
        if _normalized(item) in normalized:
            failures.append(f"response contains prohibited phrase: {item}")
    sentences = [item for item in re.split(r"[.!?]+", response) if item.strip()]
    if len(sentences) > expected.max_sentences:
        failures.append(
            f"response has {len(sentences)} sentences; maximum is {expected.max_sentences}"
        )
    return not failures, failures


def score_turn(
    turn: EvalTurn,
    *,
    trace: list[dict],
    response: str,
    state: dict,
    before_state_hash: str,
) -> dict:
    """Score deterministic Tool, response, and resulting-state expectations."""
    calls = Counter(item["tool"] for item in trace if item["kind"] == "tool_call")
    tool_failures = []
    for tool, expectation in turn.expected_tools.items():
        if isinstance(expectation, int):
            if calls[tool] != expectation:
                tool_failures.append(
                    f"expected {tool} x{expectation}, observed x{calls[tool]}"
                )
        elif not expectation.minimum <= calls[tool] <= expectation.maximum:
            tool_failures.append(
                f"expected {tool} x{expectation.minimum}..{expectation.maximum}, "
                f"observed x{calls[tool]}"
            )
    for tool in turn.prohibited_tools:
        if calls[tool]:
            tool_failures.append(f"prohibited tool called: {tool}")

    state_expectation = turn.expected_state
    tasks = state["tasks"]
    state_failures = []
    if state_expectation.task_count is not None and len(tasks) != state_expectation.task_count:
        state_failures.append(
            f"expected {state_expectation.task_count} tasks, observed {len(tasks)}"
        )
    normalized_titles = [_normalized(task["title"]) for task in tasks]
    for fragment in state_expectation.task_titles_contain:
        if not any(_normalized(fragment) in title for title in normalized_titles):
            state_failures.append(f"no Task title contains: {fragment}")
    aliases = state["aliases"]
    for alias, expected_status in state_expectation.task_statuses.items():
        actual = aliases.get(alias, {}).get("status")
        if actual != expected_status:
            state_failures.append(
                f"{alias} status expected {expected_status}, observed {actual}"
            )
    for alias, expected_due_date in state_expectation.task_due_dates.items():
        actual = aliases.get(alias, {}).get("due_date")
        if actual != expected_due_date:
            state_failures.append(
                f"{alias} due date expected {expected_due_date}, observed {actual}"
            )
    if (
        state_expectation.pending_reminder_count is not None
        and len(state["pending_reminders"]) != state_expectation.pending_reminder_count
    ):
        state_failures.append(
            "expected "
            f"{state_expectation.pending_reminder_count} pending Reminders, observed "
            f"{len(state['pending_reminders'])}"
        )
    if state_expectation.unchanged and state["state_hash"] != before_state_hash:
        state_failures.append("domain state changed despite unchanged expectation")

    response_passed, response_failures = _response_checks(response, turn.response)
    english_passed = not (
        turn.response.english
        and (re.search(r"[\u0900-\u097f]", response) or not re.search("[A-Za-z]", response))
    )
    sentences = [item for item in re.split(r"[.!?]+", response) if item.strip()]
    normalized_response = _normalized(response)
    tone_passed = len(sentences) <= turn.response.max_sentences and not any(
        phrase in normalized_response
        for phrase in ("you failed", "you should have", "disappointed in you", "lazy")
    )
    factual_passed = response_passed
    clarification_passed = True
    clarification_failures = []
    if turn.clarification == "required":
        if state_expectation.unchanged and state["state_hash"] != before_state_hash:
            clarification_failures.append("domain mutation occurred before required clarification")
            clarification_passed = False
        if "?" not in response:
            clarification_failures.append("response does not ask for required clarification")
            clarification_passed = False

    failures = [
        *tool_failures,
        *state_failures,
        *response_failures,
        *clarification_failures,
    ]
    no_unnecessary_mutation_passed = not any(
        calls[tool] for tool in turn.prohibited_tools if tool in MUTATING_TOOLS
    ) and not (
        state_expectation.unchanged and state["state_hash"] != before_state_hash
    )

    return {
        "passed": not failures,
        "tool_calls": dict(calls),
        "tool_state_passed": not tool_failures and not state_failures,
        "task_extraction_passed": not state_failures,
        "clarification_passed": clarification_passed,
        "no_unnecessary_mutation_passed": no_unnecessary_mutation_passed,
        "english_passed": english_passed,
        "factual_consistency_passed": factual_passed,
        "tone_passed": tone_passed,
        "response_passed": response_passed,
        "failures": failures,
    }


def summarize_scores(executions: list[dict], thresholds: dict[str, float]) -> dict:
    """Aggregate only applicable metric observations; categories cannot hide each other."""
    observations: dict[str, list[bool]] = {metric: [] for metric in thresholds}
    for execution in executions:
        for metric, passed in execution["metric_results"].items():
            observations[metric].append(passed)
    summary = {}
    for metric, threshold in thresholds.items():
        values = observations[metric]
        score = sum(values) / len(values) if values else 0.0
        summary[metric] = {
            "passed": bool(values) and score >= threshold,
            "score": score,
            "passed_observations": sum(values),
            "observations": len(values),
            "threshold": threshold,
        }
    return summary
