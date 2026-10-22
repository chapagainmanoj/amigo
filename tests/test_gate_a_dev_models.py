"""Development model evidence cannot be promoted into Gemini Gate A evidence."""

import pytest

from scripts.check_gate_a_evidence import ROOT, check_evidence
from scripts.run_gate_a_eval import _release_inputs
from src.evaluation.gate_a import is_gemini_model, load_suite
from tests.gate_a_fixtures import passing_gate_a_evidence


@pytest.mark.parametrize("model", ["claude-cli:sonnet", "ollama:qwen3:4b", "anthropic:claude-x"])
def test_non_gemini_cannot_certify_even_when_labelled_as_release(model):
    revision = "0" * 39 + "a"
    evidence = passing_gate_a_evidence(revision)
    evidence["release_inputs"]["model"] = model
    evidence["release_inputs"]["provider_model"] = model
    errors = check_evidence(evidence, revision=revision, root=ROOT, model_name=model)
    assert "Non-Gemini development evidence cannot certify Gate A" in errors


def test_dev_evidence_records_exact_model_id(monkeypatch):
    from scripts import run_gate_a_eval

    monkeypatch.setattr(run_gate_a_eval.settings, "dev_model", "ollama:qwen3:4b")
    suite_path = ROOT / "evals/gate_a/v1/cases.json"
    release = _release_inputs(suite_path, load_suite(suite_path))
    assert release["model"] == release["provider_model"] == "ollama:qwen3:4b"
    explicit = _release_inputs(suite_path, load_suite(suite_path), model_name="gemini-3.5-flash")
    assert explicit["provider_model"] == "google:gemini-3.5-flash"


@pytest.mark.parametrize("model", ["gemini-3.5-flash", "google:gemini-3.5-flash"])
def test_gemini_route_is_certifiable(model):
    assert is_gemini_model(model)


@pytest.mark.asyncio
async def test_dev_runner_needs_no_google_key_and_marks_development(monkeypatch, tmp_path):
    import json
    from argparse import Namespace
    from unittest.mock import AsyncMock

    from scripts import run_gate_a_eval
    from src.agent.runtime import default_runtime

    monkeypatch.setattr(run_gate_a_eval.settings, "dev_model", "claude-cli:sonnet")
    monkeypatch.setattr(run_gate_a_eval.settings, "google_api_key", "")
    monkeypatch.setattr(default_runtime, "model_for", AsyncMock(return_value=object()))
    fixture = passing_gate_a_evidence("0" * 39 + "a")["executions"][0]
    monkeypatch.setattr(run_gate_a_eval, "_run_execution", AsyncMock(return_value=fixture))
    output = tmp_path / "dev.json"
    result = await run_gate_a_eval.run(Namespace(
        mode="daily", suite=None, validate_only=False, repetitions=1,
        case=fixture["case_id"], establish_baseline=False, baseline=None,
        model=None, output=output, request_interval_seconds=0, comparison_output=None,
    ))
    assert result == 0
    evidence = json.loads(output.read_text())
    assert evidence["purpose"] == "development_eval"
    assert evidence["release_inputs"]["model"] == "claude-cli:sonnet"
