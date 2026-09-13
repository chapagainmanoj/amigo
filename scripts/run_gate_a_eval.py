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

from src.agent.agent import AgentDeps, run_agent_turn  # noqa: E402
from src.commands.base import CommandContext  # noqa: E402
from src.commands.tasks import CreateTaskCommand, CreateTaskInput  # noqa: E402
from src.config import settings  # noqa: E402
from src.evaluation.gate_a import (  # noqa: E402
    GATE_A_ENVIRONMENT,
    GATE_A_POLICY,
    GATE_A_PRICING,
    PROMPT_SOURCE,
    TIME_BEHAVIOR_SOURCES,
    TURN_CONTEXT_SOURCES,
    VALIDATOR_SOURCE,
    GateASuite,
    build_baseline_comparison,
    build_gate_a_state_snapshot,
    canonical_hash,
    dependency_versions,
    execution_metric_results,
    extract_trace,
    file_set_hash,
    invalidating_inputs,
    load_suite,
    observed_model_names,
    score_turn,
    summarize_scores,
    tool_schema,
)
from src.memory.memory_store import InMemoryStore  # noqa: E402
from src.scheduler.reminders import ReminderScheduler  # noqa: E402
from src.utils import Clock  # noqa: E402

DEFAULT_SUITE = ROOT / "evals/gate_a/v1/cases.json"
INVALIDATING_INPUTS = invalidating_inputs(ROOT)
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


def _release_inputs(suite_path: Path, suite: GateASuite) -> dict:
    status = _git("status", "--porcelain=v1")
    diff = subprocess.run(
        ["git", "diff", "--binary"], cwd=ROOT, check=True, capture_output=True
    ).stdout
    schema = tool_schema()
    return {
        "git_revision": _git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(status),
        "working_tree_diff_sha256": hashlib.sha256(diff).hexdigest(),
        # The configured alias, which is a request, not an identity.
        "model": settings.default_model,
        "provider_model": (
            f"google:{settings.default_model}"
            if settings.default_model.startswith("gemini-")
            else settings.default_model
        ),
        # Filled in from what the provider reported once the run has actually spoken to it.
        "observed_model_names": [],
        "model_settings": {},
        "dependency_versions": dependency_versions(),
        "prompt_source_sha256": hashlib.sha256((ROOT / PROMPT_SOURCE).read_bytes()).hexdigest(),
        "tool_schema_sha256": canonical_hash(schema),
        "tool_schema": schema,
        "turn_context_source_sha256": file_set_hash(
            [ROOT / relative for relative in TURN_CONTEXT_SOURCES], ROOT
        ),
        "time_behavior_source_sha256": file_set_hash(
            [ROOT / relative for relative in TIME_BEHAVIOR_SOURCES], ROOT
        ),
        "all_invalidating_inputs_sha256": file_set_hash(INVALIDATING_INPUTS, ROOT),
        "case_set_sha256": hashlib.sha256(suite_path.read_bytes()).hexdigest(),
        "case_set_version": suite.version,
        "fixed_utc": suite.fixed_utc,
        "timezone": suite.timezone,
        "validator_source_sha256": hashlib.sha256(
            (ROOT / VALIDATOR_SOURCE).read_bytes()
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
    return build_gate_a_state_snapshot(
        list(store._tasks.values()), list(store._reminders.values()), aliases
    )


async def _run_execution(case, suite: GateASuite, repetition: int, provider_model) -> dict:
    store, deps, aliases = await _setup_case(case, suite, repetition)
    observed_models: set[str] = set()
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
        messages = result.new_messages()
        trace, response = extract_trace(messages)
        observed_models.update(observed_model_names(messages))
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
                "before_state_hash": before["state_hash"],
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
        total_input * GATE_A_PRICING["input_per_million_tokens"]
        + total_output * GATE_A_PRICING["output_per_million_tokens"]
    ) / 1_000_000
    metric_results = execution_metric_results(case, turn_scores)
    return {
        "case_id": case.id,
        "category": case.category,
        "repetition": repetition,
        "observed_model_names": sorted(observed_models),
        "status": "completed",
        # Per-execution passage is derived from the independently scored metrics. The release
        # verdict is derived from their category thresholds across all executions below.
        "passed": all(metric_results.values()),
        "metric_results": metric_results,
        "turns": turn_evidence,
        "latency_ms": round((time.perf_counter() - started) * 1_000, 2),
        "usage": {"input_tokens": total_input, "output_tokens": total_output},
        "estimated_cost_usd": round(cost, 8),
    }


def _merge_observed_model_names(release_inputs: dict, execution: dict) -> None:
    """Accumulate provider identities without assuming an errored execution has one."""
    release_inputs["observed_model_names"] = sorted(
        set(release_inputs["observed_model_names"])
        | set(execution.get("observed_model_names") or [])
    )


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
    baseline = None
    baseline_sha256 = None
    if args.case and args.establish_baseline:
        raise SystemExit("--establish-baseline cannot be combined with --case")
    if args.establish_baseline and args.baseline is not None:
        raise SystemExit("--establish-baseline cannot be combined with --baseline")
    if not args.case and not args.establish_baseline:
        if args.baseline is None:
            raise SystemExit(
                "--baseline is required for a declared run; supply the archived last-passing "
                "Gate A JSON artifact"
            )
        try:
            baseline_bytes = args.baseline.read_bytes()
            baseline = json.loads(baseline_bytes)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SystemExit(f"cannot read Gate A baseline {args.baseline}: {error}") from error
        baseline_inputs = baseline.get("release_inputs") if isinstance(baseline, dict) else None
        baseline_revision = (
            baseline_inputs.get("git_revision") if isinstance(baseline_inputs, dict) else None
        )
        from scripts.check_gate_a_evidence import check_evidence

        baseline_errors = check_evidence(
            baseline,
            revision=baseline_revision or "",
            root=ROOT,
            suite_path=suite_path,
            _historical_baseline=True,
        )
        if baseline_errors:
            formatted = "\n".join(f"- {error}" for error in baseline_errors)
            raise SystemExit(f"the supplied Gate A baseline is not passing:\n{formatted}")
        baseline_sha256 = hashlib.sha256(baseline_bytes).hexdigest()
    release_inputs = _release_inputs(suite_path, suite)
    evidence = {
        "run_id": str(uuid.uuid4()),
        "suite_id": suite.suite_id,
        "purpose": (
            "development_case"
            if args.case
            else "baseline"
            if args.establish_baseline
            else "release_candidate"
        ),
        "declared_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "status": "running",
        "environment": GATE_A_ENVIRONMENT,
        "minimum_provider_request_interval_seconds": args.request_interval_seconds,
        "repetitions": args.repetitions,
        "selected_cases": [case.id for case in selected],
        "release_inputs": release_inputs,
        "pricing": GATE_A_PRICING,
        "executions": [],
        "scores": None,
        "passed": False,
        "policy": GATE_A_POLICY,
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
                    "observed_model_names": [],
                }
            evidence["executions"].append(execution)
            _merge_observed_model_names(release_inputs, execution)
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
    if baseline is not None and baseline_sha256 is not None:
        comparison_output = args.comparison_output or args.output.with_name(
            f"{args.output.stem}.comparison.json"
        )
        comparison = build_baseline_comparison(
            evidence,
            baseline,
            candidate_artifact_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
            baseline_artifact_sha256=baseline_sha256,
        )
        _write_evidence(comparison_output, comparison)
        print(
            f"baseline comparison written to {comparison_output}; "
            "release evidence remains pending until its human_review is completed"
        )
    print(json.dumps({"status": evidence["status"], **evidence["totals"]}, indent=2))
    return 0 if evidence["passed"] else 1


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/gate-a/latest.json")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Archived full JSON artifact for the last passing declared Gate A run",
    )
    parser.add_argument(
        "--establish-baseline",
        action="store_true",
        help=(
            "Run the full suite to establish the first archived baseline; this output cannot "
            "serve as release-candidate evidence"
        ),
    )
    parser.add_argument(
        "--comparison-output",
        type=Path,
        help="Comparison report path (defaults beside --output)",
    )
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
