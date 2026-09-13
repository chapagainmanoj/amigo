"""One builder for a complete, passing declared Gate A run.

Shared so the currency checker and the release-evidence manifest are tested against the same
shape `scripts/run_gate_a_eval.py` actually writes — including the execution ``status`` string
the runner really emits, which an earlier hand-written fixture got wrong.
"""

from pathlib import Path

from scripts.check_gate_a_evidence import ROOT, current_fingerprints
from src.config import settings
from src.evaluation.gate_a import THRESHOLDS, load_suite, summarize_scores

SUITE_PATH: Path = ROOT / "evals/gate_a/v1/cases.json"


def passing_gate_a_evidence(revision: str) -> dict:
    suite = load_suite(SUITE_PATH)
    executions = [
        {
            "case_id": case.id,
            "category": case.category,
            "repetition": repetition,
            "status": "completed",
            "passed": True,
            "metric_results": {metric: True for metric in case.metrics},
            "latency_ms": 1200,
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "estimated_cost_usd": 0.0006,
        }
        for case in suite.cases
        for repetition in (1, 2, 3)
    ]
    return {
        "run_id": "11111111-1111-4111-8111-111111111111",
        "suite_id": suite.suite_id,
        "status": "passed",
        "passed": True,
        "completed_at": "2026-09-13T04:15:00+00:00",
        "repetitions": 3,
        "selected_cases": [case.id for case in suite.cases],
        "release_inputs": {
            "git_revision": revision,
            "working_tree_dirty": False,
            "model": settings.default_model,
            **current_fingerprints(ROOT, SUITE_PATH),
        },
        "executions": executions,
        "scores": summarize_scores(executions, THRESHOLDS),
    }
