#!/usr/bin/env python3
"""Run every live Mode's declared scripted subset; this is never provider/Gate A evidence."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart  # noqa: E402
from pydantic_ai.models.function import FunctionModel  # noqa: E402

from scripts.run_gate_a_eval import _setup_case, _state  # noqa: E402
from src.agent.catalogue import build_registry  # noqa: E402
from src.evaluation.gate_a import extract_trace, load_mode_suite, score_turn  # noqa: E402
from src.turns import default_turn_orchestrator  # noqa: E402


async def evaluate_mode(mode) -> list[str]:
    suite_path = ROOT / mode.eval_suite
    suite = load_mode_suite(suite_path, mode.id)
    subset = json.loads(suite_path.with_name("deterministic.json").read_text())
    if subset.get("schema_version") != 1 or not subset.get("cases"):
        raise ValueError(f"Mode {mode.id} has no deterministic evaluation cases")
    by_id = {case.id: case for case in suite.cases}
    seen = set()
    failures = []
    for entry in subset["cases"]:
        case_id = entry["case_id"]
        if case_id in seen or case_id not in by_id:
            raise ValueError(f"Mode {mode.id} deterministic case {case_id} is duplicate or unknown")
        seen.add(case_id)
        case = by_id[case_id]
        store, context, aliases = await _setup_case(case, suite, 1)
        responses = list(entry["responses"])

        def scripted(messages, info, responses=responses, aliases=aliases):
            if not responses:
                raise ValueError("scripted case exhausted its declared responses")
            response = responses.pop(0)
            if "text" in response:
                return ModelResponse(parts=[TextPart(response["text"])])
            args = {
                key: aliases[value.removeprefix("$task:")]
                if isinstance(value, str) and value.startswith("$task:")
                else value
                for key, value in response["args"].items()
            }
            return ModelResponse(parts=[ToolCallPart(response["tool"], args)])

        for index, turn in enumerate(case.turns, start=1):
            context.turn_id = f"deterministic:{mode.id}:{case_id}:{index}"
            before = _state(store, aliases)
            result = await default_turn_orchestrator.run_turn(
                context, turn.message, requested_mode=mode.id, model=FunctionModel(scripted)
            )
            trace, response = extract_trace(result.messages)
            score = score_turn(
                turn,
                trace=trace,
                response=response,
                state=_state(store, aliases),
                before_state_hash=before["state_hash"],
            )
            if not score["passed"]:
                failures.append(f"{mode.id}/{case_id}/{index}: {score['failures']}")
        if responses:
            failures.append(f"{mode.id}/{case_id}: unused scripted responses")
    return failures


async def run(mode_id: str | None = None) -> int:
    registry = build_registry()
    modes = [await registry.get(mode_id)] if mode_id is not None else await registry.live()
    failures = []
    for mode in modes:
        if mode.status != "live":
            raise ValueError(f"Mode {mode.id!r} is not live")
        failures.extend(await evaluate_mode(mode))
    if failures:
        print("\n".join(failures))
        return 1
    print(f"passed deterministic subsets for {', '.join(mode.id for mode in modes)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", help="One live Mode; omitted runs all live Modes")
    raise SystemExit(asyncio.run(run(parser.parse_args().mode)))
