"""Read-only laundry comparison using labelled fictional weather, never a live source."""

from datetime import UTC, timedelta
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import FunctionToolset, RunContext

from src.tools.context import ToolContext

LAUNDRY: FunctionToolset[ToolContext] = FunctionToolset(max_retries=0)
DryingOption = Literal["dryer", "outdoor", "indoor"]
WeatherFixture = Literal["rain", "dry", "unavailable", "stale", "wrong_interval", "not_selected"]
NOTICE = "Simulated weather demonstration only; no live forecast or guaranteed drying time."


@LAUNDRY.tool
async def compare_laundry_options(
    ctx: RunContext[ToolContext],
    drying_options: list[DryingOption],
    deadline: Literal["urgent", "flexible", "unknown"],
    dryer_suitable: bool | None = None,
    prefer_outdoor: bool = False,
    require_outdoor: bool = False,
    weather_fixture: WeatherFixture = "not_selected",
    available_minutes: Annotated[int | None, Field(ge=1, le=10080)] = None,
) -> dict:
    """Compare only participant-stated laundry options in an explicitly fictional scenario.

    Weather fixtures are synthetic, never current conditions. Use only the fixture the
    participant chose; not_selected means ask before using fictional weather. No location,
    transcript, Task, preference storage, purchase or external-source access is supported.
    dryer_suitable must be explicitly known before suggesting a dryer. require_outdoor is
    a hard restriction; prefer_outdoor is a soft preference. Advice creates no Task/Reminder.
    """
    options = set(drying_options)
    result = {
        "scope": "fictional_laundry_demo",
        "notice": NOTICE,
        "outcome": "clarify",
        "recommendation": None,
        "alternative": None,
        "reason": "",
        "weather": None,
        "effects": [],
    }
    if not options:
        result["reason"] = "Which drying options are actually available?"
        return result
    if deadline == "unknown":
        result["reason"] = "Is the deadline urgent or flexible?"
        return result
    if deadline == "urgent" and available_minutes is None:
        result["reason"] = "How many minutes are available before the clothes are needed?"
        return result
    if require_outdoor:
        options &= {"outdoor"}
        if not options:
            result.update(
                outcome="abstain", reason="No available option meets the outdoor-only restriction."
            )
            return result
    suitable_dryer = "dryer" in options and dryer_suitable is True
    if options == {"dryer"}:
        if dryer_suitable is None:
            result["reason"] = "Are these clothes suitable for the available dryer?"
        elif not suitable_dryer:
            result.update(outcome="abstain", reason="The only available dryer is unsuitable.")
        else:
            result.update(
                outcome="recommend",
                recommendation="dryer",
                reason="The available dryer is suitable; completion time is unverified.",
            )
        return result
    if "outdoor" not in options:
        if suitable_dryer:
            result.update(
                outcome="recommend",
                recommendation="dryer",
                reason="The available dryer is suitable; completion time is unverified.",
                alternative="indoor" if "indoor" in options else None,
            )
        elif "indoor" in options:
            result.update(
                outcome="recommend",
                recommendation="indoor",
                reason="Indoor drying is available; completion time is unverified.",
            )
        else:
            result.update(outcome="abstain", reason="No supported drying option is available.")
        return result
    if weather_fixture == "not_selected":
        result["reason"] = "Which fictional weather scenario should we compare: rain or dry?"
        return result
    now = ctx.deps.clock.utc_now().replace(tzinfo=UTC)
    result["weather"] = {
        "source": "Amigo fictional laundry fixtures v1",
        "fixture_id": weather_fixture,
        "simulated": True,
        "location": "fictional demo area",
        "retrieved_at": now.isoformat(),
        "forecast_interval": "fictional available drying window",
        "fresh_until": (now + timedelta(hours=1)).isoformat(),
    }
    if weather_fixture in {"unavailable", "stale", "wrong_interval"}:
        if weather_fixture == "stale":
            result["weather"]["fresh_until"] = (now - timedelta(seconds=1)).isoformat()
        result.update(
            outcome="abstain", reason="Weather evidence is unavailable or outside its window."
        )
        return result
    if weather_fixture == "rain":
        if suitable_dryer:
            result.update(
                outcome="recommend",
                recommendation="dryer",
                reason="Simulated rain conflicts with outdoors; a suitable dryer exists.",
            )
        elif deadline == "flexible":
            result.update(
                outcome="recommend",
                recommendation="postpone",
                reason="Simulated rain conflicts with outdoors; the deadline is flexible.",
            )
        elif "indoor" in options:
            result.update(
                outcome="recommend",
                recommendation="indoor",
                reason="Consider available indoor drying; completion time is unverified.",
            )
        else:
            result.update(
                outcome="abstain", reason="No supported option meets the urgent constraints."
            )
    else:
        choice = "outdoor" if prefer_outdoor or not suitable_dryer else "dryer"
        result.update(
            outcome="recommend",
            recommendation=choice,
            reason="Compare options using simulated dry weather; timing is uncertain.",
            alternative="dryer" if choice == "outdoor" and suitable_dryer else None,
        )
    return result
