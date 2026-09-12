"""Static guardrails for the single-owner beta deployment topology."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PARTS = {"archive", ".scratch"}


def _render_services() -> list[str]:
    blueprint = (ROOT / "render.yaml").read_text()
    return [block for block in blueprint.split("\n  - type: ")[1:] if block.strip()]


def test_fly_cannot_be_deployed_from_default_repository_paths():
    active_fly_configs = [
        path
        for path in ROOT.rglob("fly.toml")
        if not ARCHIVE_PARTS.intersection(path.relative_to(ROOT).parts)
    ]
    assert active_fly_configs == []

    active_workflows = list((ROOT / ".github" / "workflows").glob("*.y*ml"))
    deployment_sources = active_workflows + list((ROOT / "scripts").glob("*"))
    forbidden_markers = ("flyctl", "FLY_API_TOKEN", "superfly/", "amigo.fly.dev")
    for source in deployment_sources:
        if not source.is_file():
            continue
        content = source.read_text(errors="ignore")
        assert not any(marker in content for marker in forbidden_markers), source


def test_render_blueprint_declares_one_telegram_application_owner():
    services = _render_services()
    application_services = [block for block in services if "staticPublishPath:" not in block]
    static_services = [block for block in services if "staticPublishPath:" in block]

    assert len(application_services) == 1
    assert len(static_services) == 1
    application = application_services[0]
    assert "name: amigo\n" in application
    assert "runtime: docker" in application
    assert "healthCheckPath: /health" in application
    assert "key: APP_CHANNEL\n        value: telegram" in application


def test_archived_fly_material_is_explicitly_disabled():
    config = (ROOT / "deploy" / "archive" / "fly.toml.disabled").read_text()
    workflow = (ROOT / ".github" / "archive" / "deploy-fly.yml.disabled").read_text()
    assert "Deliberately disabled" in config
    assert "if: ${{ false }}" in workflow
