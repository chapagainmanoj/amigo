"""Owner model routing cannot silently expand model/provider release authorization."""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from scripts.check_gate_a_evidence import check_evidence
from src.agent.catalogue import DAILY, build_registry
from src.agent.runtime import ModeRuntime, _provider_for
from src.config import Settings
from src.evaluation.model_policy import fallback_currency, require_evaluated_model
from src.model_routing import resolve_model
from src.runtime_config import UnsafeProductionConfigurationError, validate_runtime_configuration
from tests.fakes import FakeStore
from tests.gate_a_fixtures import passing_gate_a_evidence
from tests.test_modes import _deliver, _participant
from tests.test_runtime_config import _production_config


@pytest.mark.parametrize(
    ("dev", "pin", "mode", "expected"),
    [
        ("claude-cli:sonnet", True, True, "claude-cli:sonnet"),
        ("", True, True, "anthropic:claude-haiku-5-5"),
        ("", False, True, "google:gemini-mode"),
        ("", False, False, "google:gemini-default"),
    ],
)
def test_precedence(dev, pin, mode, expected):
    config = Settings(
        _env_file=None,
        default_model="gemini-default",
        dev_model=dev,
        participant_model_pins={"internal": "anthropic:claude-haiku-5-5"} if pin else {},
        mode_models="daily=google:gemini-mode" if mode else "",
    )
    assert resolve_model(config, mode_id="daily", user_id="internal") == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"default_model": "unknown:private-value"},
        {"dev_model": "unknown:private-value"},
        {"default_model": "claude"},
        {"default_model": "google:"},
        {"mode_models": "daily=unknown:private-value"},
        {"participant_model_pins": "internal=unknown:private-value"},
        {"mode_models": "daily=google:a,daily=google:b"},
        {"mode_models": "broken"},
    ],
)
def test_invalid_models_fail_startup_without_values(kwargs):
    with pytest.raises((UnsafeProductionConfigurationError, ValidationError)) as error:
        config = Settings(_env_file=None, **kwargs)
        validate_runtime_configuration(config)
    assert "private-value" not in str(error.value)


def test_environment_maps_accept_comma_config(monkeypatch):
    monkeypatch.setenv("MODE_MODELS", "daily=google:gemini-mode")
    assert Settings(_env_file=None).mode_models == {"daily": "google:gemini-mode"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dev_model": "ollama:qwen3:4b"},
        {"default_model": "claude-cli:sonnet"},
        {"mode_models": {"daily": "claude-cli:sonnet"}},
        {"participant_model_pins": {"internal": "claude-cli:sonnet"}},
    ],
)
def test_production_never_allows_subscription_cli(kwargs):
    with pytest.raises(UnsafeProductionConfigurationError):
        validate_runtime_configuration(_production_config(**kwargs))


def test_production_override_requires_per_mode_model_evidence():
    with pytest.raises(UnsafeProductionConfigurationError, match="evaluation evidence"):
        validate_runtime_configuration(
            _production_config(
                mode_models="daily=anthropic:claude-x", approved_model_providers="google,anthropic"
            )
        )


async def test_anthropic_provider_uses_platform_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch(
        "src.config.settings", Settings(_env_file=None, anthropic_api_key="platform-secret")
    ):
        provider = _provider_for("anthropic")
        model = await ModeRuntime(build_registry()).model_for("anthropic:claude-haiku-5-5")
    assert provider.client.api_key == "platform-secret"
    assert model.client.api_key == "platform-secret"


async def test_resolved_model_is_recorded_without_logging_pin_user_or_key(caplog):
    store = FakeStore()
    user = await _participant(store, 1001)
    config = Settings(
        _env_file=None,
        participant_model_pins={user["user_id"]: "anthropic:claude-haiku-5-5"},
        anthropic_api_key="private-platform-key",
    )
    runtime = ModeRuntime(build_registry())
    scripted = FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("Hello")]))
    with patch("src.config.settings", config), caplog.at_level("INFO"):
        async with runtime.override(model=scripted):
            await _deliver(store, "Hello", 1001, runtime)
    records = [record.turn_record for record in caplog.records if hasattr(record, "turn_record")]
    assert records[0]["requested_model"] == "anthropic:claude-haiku-5-5"
    pin_messages = [
        record.getMessage()
        for record in caplog.records
        if "owner_internal_model_pin" in record.getMessage()
    ]
    assert pin_messages and user["user_id"] not in pin_messages[0]
    assert "private-platform-key" not in caplog.text


def _artifact(tmp_path, model="anthropic:claude-x"):
    root = Path(__file__).resolve().parents[1]
    evidence = passing_gate_a_evidence("a" * 40)
    evidence["purpose"] = "development_eval"
    from src.agent.modes import PLACEHOLDER_FACTS
    from src.evaluation.gate_a import canonical_hash

    evidence["release_inputs"].update(
        model=model,
        provider_model=model,
        mode_instructions_sha256=canonical_hash(DAILY.instructions(PLACEHOLDER_FACTS)),
    )
    currency = fallback_currency(DAILY, root)
    evidence["release_inputs"]["fallback_currency"] = currency
    (tmp_path / "evals/gate_a/v1").mkdir(parents=True)
    (tmp_path / "evals/gate_a/v1/cases.json").write_bytes((root / DAILY.eval_suite).read_bytes())
    return evidence, currency


def _save(tmp_path, evidence, review=True):
    artifact = json.dumps(evidence).encode()
    digest = hashlib.sha256(artifact).hexdigest()
    (tmp_path / "model.json").write_bytes(artifact)
    entry = {
        "mode_id": "daily",
        "model": evidence["release_inputs"]["model"],
        "artifact": "model.json",
        "sha256": digest,
    }
    if review:
        entry["human_review"] = {
            "status": "approved",
            "artifact_sha256": digest,
            "reviewer": "owner",
            "reviewed_at": "2026-09-03T01:00:00+00:00",
            "tone_reviewed": True,
            "notes": "Reviewed all subjective results and failures.",
        }
    (tmp_path / "evals/model-evidence.json").write_text(json.dumps({"entries": [entry]}))


def test_non_gemini_full_evidence_can_allow_model_but_never_gate_a(tmp_path):
    evidence, currency = _artifact(tmp_path)
    _save(tmp_path, evidence)
    with (
        patch("src.evaluation.model_policy.fallback_currency", return_value=currency),
        patch("scripts.check_gate_a_evidence.current_fingerprints", return_value={}),
    ):
        require_evaluated_model(DAILY, "anthropic:claude-x", tmp_path)
        errors = check_evidence(
            evidence,
            revision="a" * 40,
            root=tmp_path,
            suite_path=tmp_path / DAILY.eval_suite,
            mode_definition=DAILY,
            _historical_baseline=True,
        )
    assert "Non-Gemini development evidence cannot certify Gate A" in errors


@pytest.mark.parametrize(
    "mutation", ["failed", "incomplete", "stale", "identity", "review", "instructions", "tools"]
)
def test_model_allowlist_rejects_failures_stale_or_wrong_inputs_and_unreviewed(tmp_path, mutation):
    evidence, currency = _artifact(tmp_path)
    if mutation == "failed":
        evidence["executions"][0]["turns"][0]["response"] = "you failed"
    elif mutation == "incomplete":
        evidence["executions"].pop()
    elif mutation == "stale":
        evidence["release_inputs"]["fallback_currency"] = {}
    elif mutation == "identity":
        evidence["release_inputs"]["provider_model"] = "google:gemini-test"
    elif mutation == "instructions":
        evidence["release_inputs"]["mode_instructions_sha256"] = "0" * 64
    elif mutation == "tools":
        evidence["release_inputs"]["tool_schema_sha256"] = "0" * 64
    _save(tmp_path, evidence, review=mutation != "review")
    with (
        patch("src.evaluation.model_policy.fallback_currency", return_value=currency),
        patch("scripts.check_gate_a_evidence.current_fingerprints", return_value={}),
        pytest.raises(ValueError, match="no current passing evaluation"),
    ):
        require_evaluated_model(DAILY, "anthropic:claude-x", tmp_path)


async def test_cached_cli_is_refused_after_production_configuration_change():
    runtime = ModeRuntime(build_registry())
    with patch("src.config.settings", Settings(_env_file=None)):
        await runtime.model_for("claude-cli:sonnet")
    with (
        patch("src.config.settings", Settings(_env_file=None, app_env="production")),
        pytest.raises(ValueError, match="development-only"),
    ):
        await runtime.model_for("claude-cli:sonnet")


@pytest.mark.parametrize("mutation", ["sha", "review-sha", "review-future", "review-null"])
def test_model_manifest_hash_and_review_are_enforced(tmp_path, mutation):
    evidence, currency = _artifact(tmp_path)
    _save(tmp_path, evidence)
    manifest_path = tmp_path / "evals/model-evidence.json"
    manifest = json.loads(manifest_path.read_text())
    entry = manifest["entries"][0]
    if mutation == "sha":
        entry["sha256"] = "0" * 64
    elif mutation == "review-sha":
        entry["human_review"]["artifact_sha256"] = "0" * 64
    elif mutation == "review-future":
        entry["human_review"]["reviewed_at"] = "2100-01-01T00:00:00+00:00"
    else:
        entry["human_review"] = None
    manifest_path.write_text(json.dumps(manifest))
    with (
        patch("src.evaluation.model_policy.fallback_currency", return_value=currency),
        pytest.raises(ValueError, match="no current passing evaluation"),
    ):
        require_evaluated_model(DAILY, "anthropic:claude-x", tmp_path)


def test_model_review_naive_utc_clock_is_not_interpreted_in_host_timezone(tmp_path, monkeypatch):
    import time
    from datetime import datetime

    evidence, currency = _artifact(tmp_path)
    _save(tmp_path, evidence)
    try:
        with monkeypatch.context() as clock_patch:
            clock_patch.setenv("TZ", "Asia/Kathmandu")
            time.tzset()
            clock_patch.setattr(
                "src.utils.utc_now",
                lambda: datetime(2026, 9, 3, 1, 0, 1),
            )
            with (
                patch("src.evaluation.model_policy.fallback_currency", return_value=currency),
                patch("scripts.check_gate_a_evidence.current_fingerprints", return_value={}),
            ):
                require_evaluated_model(DAILY, "anthropic:claude-x", tmp_path)
    finally:
        time.tzset()



@pytest.mark.parametrize(
    ("reference", "setting", "key"),
    [
        ("openai:gpt-small", "openai_api_key", "openai-platform-secret"),
        ("deepseek:deepseek-chat", "deepseek_api_key", "deepseek-platform-secret"),
    ],
)
async def test_openai_compatible_providers_use_their_platform_keys(reference, setting, key):
    with patch("src.config.settings", Settings(_env_file=None, **{setting: key})):
        model = await ModeRuntime(build_registry()).model_for(reference)
    assert type(model).__name__ == "OpenAIChatModel"
    assert model.model_name == reference.partition(":")[2]
    assert model.client.api_key == key


def test_flash_lite_is_an_ordinary_google_route():
    config = Settings(_env_file=None, default_model="gemini-3.5-flash-lite")
    assert resolve_model(config, mode_id="daily") == "google:gemini-3.5-flash-lite"


@pytest.mark.parametrize(
    ("kwargs", "missing"),
    [
        ({"default_model": "openai:gpt-small"}, "OPENAI_API_KEY"),
        ({"default_model": "deepseek:deepseek-chat"}, "DEEPSEEK_API_KEY"),
        ({"mode_models": "coach=openai:gpt-small"}, "OPENAI_API_KEY"),
        ({"dev_model": "deepseek:deepseek-chat"}, "DEEPSEEK_API_KEY"),
    ],
)
def test_each_routed_provider_requires_its_own_key(kwargs, missing):
    from src.runtime_config import require_agent_credentials

    with pytest.raises(UnsafeProductionConfigurationError, match=missing):
        require_agent_credentials(Settings(_env_file=None, google_api_key="g" * 30, **kwargs))


def test_non_google_default_needs_no_google_key():
    from src.runtime_config import require_agent_credentials

    require_agent_credentials(
        Settings(_env_file=None, default_model="openai:gpt-small", openai_api_key="o" * 30)
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"default_model": "openai:gpt-small", "openai_api_key": "o" * 30},
        {"default_model": "deepseek:deepseek-chat", "deepseek_api_key": "d" * 30},
        {"mode_models": "daily=openai:gpt-small", "openai_api_key": "o" * 30},
    ],
)
def test_production_refuses_unapproved_processor(kwargs):
    with pytest.raises(UnsafeProductionConfigurationError, match="APPROVED_MODEL_PROVIDERS"):
        validate_runtime_configuration(_production_config(**kwargs))


def test_production_approved_non_gemini_default_still_needs_live_mode_evidence():
    with pytest.raises(UnsafeProductionConfigurationError, match="every live Mode"):
        validate_runtime_configuration(
            _production_config(
                default_model="openai:gpt-small",
                openai_api_key="o" * 30,
                approved_model_providers="google,openai",
            )
        )


def test_production_flash_lite_default_is_allowed():
    validate_runtime_configuration(_production_config(default_model="gemini-3.5-flash-lite"))


def test_owner_pin_to_unapproved_provider_is_exempt_but_needs_key():
    config = _production_config(
        participant_model_pins={"internal": "openai:gpt-small"}, openai_api_key="o" * 30
    )
    validate_runtime_configuration(config)
