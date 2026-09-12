#!/usr/bin/env python3
"""Run the versioned Gate A model evaluation without retrying failed candidates."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic_ai.exceptions import ModelHTTPError  # noqa: E402
from pydantic_ai.models.google import GoogleModel  # noqa: E402
from pydantic_ai.providers.google import GoogleProvider  # noqa: E402

from src.agent.agent import AgentDeps, amigo_agent, run_agent_turn  # noqa: E402
from src.commands.base import CommandContext  # noqa: E402
from src.commands.tasks import CreateTaskCommand, CreateTaskInput  # noqa: E402
from src.config import settings  # noqa: E402
from src.evaluation.gate_a import (  # noqa: E402
    GateASuite,
    canonical_hash,
    extract_trace,
    file_set_hash,
    load_suite,
    score_turn,
    summarize_scores,
)
from src.memory.memory_store import InMemoryStore  # noqa: E402
from src.scheduler.reminders import ReminderScheduler  # noqa: E402
from src.utils import Clock  # noqa: E402

DEFAULT_SUITE = ROOT / "evals/gate_a/v1/cases.json"
INVALIDATING_INPUTS = [
    *sorted((ROOT / "migrations").glob("*.sql")),
    ROOT / "scripts/run_gate_a_eval.py",
    ROOT / "src/agent/agent.py",
    ROOT / "src/agent/prompts.py",
    ROOT / "src/commands/later.py",
    ROOT / "src/commands/reminders.py",
    ROOT / "src/commands/tasks.py",
    ROOT / "src/evaluation/gate_a.py",
    ROOT / "src/memory/context.py",
    ROOT / "src/memory/memory_store.py",
    ROOT / "src/memory/store.py",
    ROOT / "src/time_resolution.py",
    ROOT / "src/tools/reminders.py",
    ROOT / "src/tools/tasks.py",
    ROOT / "src/utils/__init__.py",
]
PRICING = {
    "currency": "USD",
    "input_per_million_tokens": 1.50,
    "output_per_million_tokens": 9.00,
    "source": "https://ai.google.dev/gemini-api/docs/pricing",
    "checked_on": "2026-08-31",
    "billing_tier": "paid-standard-conservative",
}


class FixedClock(Clock):
    """Evaluation clock shared by prompt and time interpretation."""

    def __init__(self, instant: datetime):
        self.instant = instant.astimezone(UTC).replace(tzinfo=None)

    def utc_now(self) -> datetime:
        return self.instant

    def now_in_tz(self, timezone: str) -> datetime:
        return self.instant.replace(tzinfo=UTC).astimezone(ZoneInfo(timezone))


class RateLimitedGoogleModel(GoogleModel):
    """Space provider requests without retrying an unchanged candidate."""

    def __init__(self, *args, minimum_interval_seconds: float, **kwargs):
        super().__init__(*args, **kwargs)
        self.minimum_interval_seconds = minimum_interval_seconds
        self._request_lock = asyncio.Lock()
        self._last_request_started = 0.0

    async def request(self, messages, model_settings, model_request_parameters):
        async with self._request_lock:
            elapsed = time.monotonic() - self._last_request_started
            remaining = self.minimum_interval_seconds - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_request_started = time.monotonic()
        return await super().request(messages, model_settings, model_request_parameters)


class EvaluationChannel:
    """No-network channel for isolated model evaluations."""

    async def send_message(self, chat_id, text, *, buttons=None) -> int:
        return 1

    async def edit_message_buttons(self, chat_id, message_id, *, buttons=None) -> None:
        return None


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _tool_schema() -> list[dict]:
    tools = []
    for name, tool in sorted(amigo_agent._function_toolset.tools.items()):
        schema = tool.function_schema
        tools.append(
            {
                "name": name,
                "description": schema.description,
                "parameters": schema.json_schema,
                "return_schema": schema.return_schema,
            }
        )
    return tools


def _release_inputs(suite_path: Path, suite: GateASuite) -> dict:
    status = _git("status", "--porcelain=v1")
    diff = subprocess.run(
        ["git", "diff", "--binary"], cwd=ROOT, check=True, capture_output=True
    ).stdout
    tool_schema = _tool_schema()
    return {
        "git_revision": _git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(status),
        "working_tree_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "model": settings.default_model,
        "provider_model": (
            f"google:{settings.default_model}"
            if settings.default_model.startswith("gemini-")
            else settings.default_model
        ),
        "model_settings": {},
        "prompt_source_sha256": hashlib.sha256(
            (ROOT / "src/agent/prompts.py").read_bytes()
        ).hexdigest(),
        "tool_schema_sha256": canonical_hash(tool_schema),
        "tool_schema": tool_schema,
        "turn_context_source_sha256": file_set_hash(
            [ROOT / "src/agent/agent.py", ROOT / "src/memory/context.py"], ROOT
        ),
        "time_behavior_source_sha256": file_set_hash(
            [
                ROOT / "src/commands/later.py",
                ROOT / "src/commands/reminders.py",
                ROOT / "src/time_resolution.py",
                ROOT / "src/utils/__init__.py",
            ],
            ROOT,
        ),
        "all_invalidating_inputs_sha256": file_set_hash(INVALIDATING_INPUTS, ROOT),
        "case_set_sha256": hashlib.sha256(suite_path.read_bytes()).hexdigest(),
        "case_set_version": suite.version,
        "fixed_utc": suite.fixed_utc,
        "timezone": suite.timezone,
        "validator_source_sha256": hashlib.sha256(
            (ROOT / "src/evaluation/gate_a.py").read_bytes()
        ).hexdigest(),
    }


async def _setup_case(case, suite: GateASuite, repetition: int):
    store = InMemoryStore()
    channel = EvaluationChannel()
    scheduler = ReminderScheduler(channel, store)
    user = await store.create_user(8_000_000 + repetition)
    user = await store.update_user(
        user["user_id"],
        {
            "name": "Eval User",
            "timezone": suite.timezone,
            "wake_time": "07:30",
            "sleep_time": "23:00",
            "onboarding_complete": True,
            "onboarding_step": 3,
        },
    )
    session = await store.create_session(user["user_id"], "casual")
    aliases = {}
    for index, setup_task in enumerate(case.setup.tasks):
        result = await CreateTaskCommand(store).run(
            CommandContext(
                user["user_id"],
                "telegram",
                f"setup:{case.id}:{repetition}:{index}",
            ),
            CreateTaskInput(title=setup_task.title, planning_day=None),
        )
        task = result["task"]
        if setup_task.status != "pending":
            task = await store.update_task_status(
                task["task_id"], setup_task.status, user["user_id"]
            )
        aliases[setup_task.alias] = task["task_id"]
        if setup_task.reminder_at:
            await store.create_reminder(
                task["task_id"], user["user_id"], setup_task.reminder_at
            )
    for item in case.setup.history:
        await store.add_message(
            session["session_id"], user["user_id"], item["role"], item["content"]
        )
    clock = FixedClock(datetime.fromisoformat(suite.fixed_utc.replace("Z", "+00:00")))
    deps = AgentDeps(
        store=store,
        scheduler=scheduler,
        channel=channel,
        user=user,
        session_id=session["session_id"],
        chat_id=8_000_000 + repetition,
        timezone=suite.timezone,
        turn_id=f"{case.id}:{repetition}:0",
        clock=clock,
    )
    return store, deps, aliases


def _state(store: InMemoryStore, aliases: dict[str, str]) -> dict:
    tasks = [
        {
            "task_id": task["task_id"],
            "title": task["title"],
            "status": task["status"],
            "due_date": task.get("due_date"),
            "version": task.get("version"),
        }
        for task in store._tasks.values()
    ]
    reminders = [
        {
            "reminder_id": reminder["reminder_id"],
            "task_id": reminder["task_id"],
            "status": reminder["status"],
            "scheduled_time": reminder["scheduled_time"],
        }
        for reminder in store._reminders.values()
        if reminder["status"] in {"pending", "sending", "sent"}
    ]
    stable = {
        "tasks": sorted(
            ({key: value for key, value in task.items() if key != "task_id"} for task in tasks),
            key=lambda item: (item["title"], item["status"]),
        ),
        "pending_reminders": sorted(
            (
                {key: value for key, value in reminder.items() if key != "reminder_id"}
                for reminder in reminders
            ),
            key=lambda item: (item["task_id"], item["scheduled_time"]),
        ),
    }
    return {
        "tasks": tasks,
        "pending_reminders": reminders,
        "aliases": {
            alias: next((task for task in tasks if task["task_id"] == task_id), {})
            for alias, task_id in aliases.items()
        },
        "state_hash": canonical_hash(stable),
    }


def _metric_results(case, turn_results: list[dict]) -> dict[str, bool]:
    def all_turns(key: str) -> bool:
        return all(result[key] for result in turn_results)

    mapping = {
        "hard_invariant": all_turns("passed"),
        "safety_boundary": all_turns("response_passed")
        and all_turns("no_unnecessary_mutation_passed"),
        "english": all_turns("english_passed"),
        "mutation_risk_clarification": all_turns("clarification_passed")
        and all_turns("no_unnecessary_mutation_passed"),
        "tool_and_state": all_turns("tool_state_passed"),
        "task_extraction": all_turns("task_extraction_passed"),
        "clarification": all_turns("clarification_passed"),
        "no_unnecessary_mutation": all_turns("no_unnecessary_mutation_passed"),
        "factual_consistency": all_turns("factual_consistency_passed"),
        "tone": all_turns("tone_passed"),
        "dependency_error_handling": all_turns("factual_consistency_passed"),
    }
    return {metric: mapping[metric] for metric in case.metrics}


async def _run_execution(case, suite: GateASuite, repetition: int, provider_model) -> dict:
    store, deps, aliases = await _setup_case(case, suite, repetition)
    turn_evidence = []
    total_input = 0
    total_output = 0
    started = time.perf_counter()
    for turn_index, turn in enumerate(case.turns, start=1):
        deps.turn_id = f"{case.id}:{repetition}:{turn_index}"
        before = _state(store, aliases)
        turn_started = time.perf_counter()
        result = await run_agent_turn(deps, turn.message, model=provider_model)
        latency_ms = round((time.perf_counter() - turn_started) * 1_000, 2)
        trace, response = extract_trace(result.new_messages())
        usage = result.usage
        total_input += usage.input_tokens
        total_output += usage.output_tokens
        after = _state(store, aliases)
        score = score_turn(
            turn,
            trace=trace,
            response=response,
            state=after,
            before_state_hash=before["state_hash"],
        )
        turn_evidence.append(
            {
                "turn": turn_index,
                "message": turn.message,
                "trace": trace,
                "response": response,
                "state": after,
                "latency_ms": latency_ms,
                "usage": {
                    "requests": usage.requests,
                    "tool_calls": usage.tool_calls,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cache_read_tokens": usage.cache_read_tokens,
                    "cache_write_tokens": usage.cache_write_tokens,
                    "details": usage.details,
                },
                "score": score,
            }
        )
    turn_scores = [item["score"] for item in turn_evidence]
    cost = (
        total_input * PRICING["input_per_million_tokens"]
        + total_output * PRICING["output_per_million_tokens"]
    ) / 1_000_000
    return {
        "case_id": case.id,
        "category": case.category,
        "repetition": repetition,
        "status": "completed",
        "passed": all(score["passed"] for score in turn_scores),
        "metric_results": _metric_results(case, turn_scores),
        "turns": turn_evidence,
        "latency_ms": round((time.perf_counter() - started) * 1_000, 2),
        "usage": {"input_tokens": total_input, "output_tokens": total_output},
        "estimated_cost_usd": round(cost, 8),
    }


def _write_evidence(path: Path, evidence: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")


async def run(args) -> int:
    suite_path = args.suite.resolve()
    suite = load_suite(suite_path)
    print(f"validated {suite.suite_id}: {len(suite.cases)} cases, {suite.repetitions} repetitions")
    if args.validate_only:
        return 0
    if not settings.google_api_key:
        raise SystemExit("GOOGLE_API_KEY is required for a declared Gate A run")
    if args.repetitions != suite.repetitions and not args.case:
        raise SystemExit("a declared Gate A run must use exactly three repetitions")

    selected = [case for case in suite.cases if not args.case or case.id == args.case]
    if not selected:
        raise SystemExit(f"unknown case: {args.case}")
    release_inputs = _release_inputs(suite_path, suite)
    evidence = {
        "run_id": str(uuid.uuid4()),
        "suite_id": suite.suite_id,
        "declared_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "status": "running",
        "environment": "controlled-local-isolated",
        "minimum_provider_request_interval_seconds": args.request_interval_seconds,
        "repetitions": args.repetitions,
        "selected_cases": [case.id for case in selected],
        "release_inputs": release_inputs,
        "pricing": PRICING,
        "executions": [],
        "scores": None,
        "passed": False,
        "policy": "No failed or unchanged execution is retried within this declared run.",
    }
    _write_evidence(args.output, evidence)

    if settings.default_model.startswith("gemini-"):
        provider_model = RateLimitedGoogleModel(
            settings.default_model,
            provider=GoogleProvider(api_key=settings.google_api_key),
            minimum_interval_seconds=args.request_interval_seconds,
        )
    else:
        provider_model = release_inputs["provider_model"]
    for case in selected:
        for repetition in range(1, args.repetitions + 1):
            print(f"running {case.id} repetition {repetition}/{args.repetitions}", flush=True)
            try:
                execution = await _run_execution(case, suite, repetition, provider_model)
            except Exception as error:
                if (
                    not args.case
                    and isinstance(error, ModelHTTPError)
                    and error.status_code == 429
                ):
                    evidence["status"] = "aborted_provider_incident"
                    evidence["completed_at"] = datetime.now(UTC).isoformat()
                    evidence.setdefault("provider_incidents", []).append(
                        {
                            "case_id": case.id,
                            "repetition": repetition,
                            "type": "quota_exhausted",
                            "status_code": 429,
                            "message": str(error)[:1_000],
                        }
                    )
                    _write_evidence(args.output, evidence)
                    print("Declared run aborted on a documented provider quota incident.")
                    return 2
                execution = {
                    "case_id": case.id,
                    "category": case.category,
                    "repetition": repetition,
                    "status": "error",
                    "passed": False,
                    "metric_results": {metric: False for metric in case.metrics},
                    "error_type": type(error).__name__,
                    "error": str(error)[:1_000],
                    "turns": [],
                    "latency_ms": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                    "estimated_cost_usd": 0.0,
                }
            evidence["executions"].append(execution)
            _write_evidence(args.output, evidence)

    scoring_thresholds = suite.thresholds
    if args.case:
        active_metrics = {metric for case in selected for metric in case.metrics}
        scoring_thresholds = {
            metric: threshold
            for metric, threshold in suite.thresholds.items()
            if metric in active_metrics
        }
    evidence["scores"] = summarize_scores(evidence["executions"], scoring_thresholds)
    evidence["passed"] = all(item["passed"] for item in evidence["scores"].values())
    evidence["status"] = "passed" if evidence["passed"] else "failed"
    evidence["completed_at"] = datetime.now(UTC).isoformat()
    evidence["totals"] = {
        "executions": len(evidence["executions"]),
        "input_tokens": sum(item["usage"]["input_tokens"] for item in evidence["executions"]),
        "output_tokens": sum(
            item["usage"]["output_tokens"] for item in evidence["executions"]
        ),
        "estimated_cost_usd": round(
            sum(item["estimated_cost_usd"] for item in evidence["executions"]), 8
        ),
    }
    _write_evidence(args.output, evidence)
    print(json.dumps({"status": evidence["status"], **evidence["totals"]}, indent=2))
    return 0 if evidence["passed"] else 1


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/gate-a/latest.json")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--case", help="Run one case for development; not release evidence")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=13.0,
        help="Minimum delay between provider requests; 13 seconds respects the 5 RPM free tier.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
