"""THROWAWAY: can stated constraints and simulated weather support useful laundry advice?

No model, I/O, persistence, production imports, or measured drying-time assumptions.
Selected methods mean the participant says they are available AND suitable for these clothes.
Weather labels are fictional fixtures, not real forecasts or approved freshness policies.
"""

from dataclasses import dataclass
from typing import Literal

Method = Literal["outdoor", "dryer", "indoor"]
Weather = Literal["clear", "rain", "missing", "stale", "wrong_location", "wrong_window"]


@dataclass(frozen=True)
class Scenario:
    methods: tuple[Method, ...] = ("outdoor",)
    # An absent indoor option is unknown until explicitly ruled out; avoid repeating a question.
    indoor_checked: bool = False
    preferred: Method | None = "outdoor"
    urgency: Literal["flexible", "urgent", "unknown"] = "flexible"
    washing_window: Literal["available", "unavailable", "unknown"] = "available"
    weather: Weather = "clear"


@dataclass(frozen=True)
class Advice:
    outcome: str
    recommendation: str
    reason: str
    alternative: str | None = None
    uncertainty: str = "Drying time and readiness by your deadline are not established."
    weather_used: bool = False


async def advise(state: Scenario) -> Advice:
    """Pure decision function. Priority rules are exploratory, not a validated product policy."""
    if not state.methods:
        return Advice("clarify", "Which suitable drying methods can you use?", "None declared.")
    if state.urgency == "unknown":
        return Advice("clarify", "When do you need the clothes ready?", "Urgency is unknown.")
    if state.washing_window == "unknown":
        return Advice("clarify", "Do you have a washing window now?", "Available time is unknown.")
    if state.washing_window == "unavailable":
        return Advice(
            "recommend",
            "Choose a later washing window.",
            "You said you cannot wash now; weather cannot remove that constraint.",
        )

    sheltered = next((method for method in ("dryer", "indoor") if method in state.methods), None)
    preferred = state.preferred if state.preferred in state.methods else None
    outdoor_candidate = "outdoor" in state.methods and (preferred == "outdoor" or sheltered is None)
    if not outdoor_candidate:
        method = preferred or sheltered
        return Advice(
            "recommend",
            f"Consider washing now with your {method} option.",
            "That option is declared suitable; outdoor weather is not needed for this comparison.",
        )

    if state.weather not in ("clear", "rain"):
        if sheltered:
            return Advice(
                "recommend",
                f"Consider your {sheltered} option instead of relying on outdoors.",
                f"The simulated forecast is {state.weather.replace('_', ' ')}; it cannot support "
                "an outdoor recommendation.",
                "Wait for usable weather evidence if outdoor drying matters more to you.",
            )
        return Advice(
            "insufficient_evidence",
            "I cannot support an outdoor-drying recommendation yet.",
            f"The simulated forecast is {state.weather.replace('_', ' ')}.",
            "Provide usable weather evidence for your location and washing/drying window.",
        )
    if state.weather == "rain":
        if "dryer" in state.methods:
            return Advice(
                "recommend",
                "Consider washing now with your dryer option.",
                "The fictional forecast expects rain during the outdoor window; this trades "
                "your outdoor preference for an available non-outdoor option.",
                "Postpone if outdoor drying matters more and your deadline allows it.",
                weather_used=True,
            )
        if state.urgency == "flexible":
            return Advice(
                "recommend",
                "Consider postponing outdoor laundry.",
                "Your deadline is flexible, no dryer is declared, and the fictional forecast "
                "expects rain. There is no need to explore indoor drying first.",
                "Reconsider when a new usable forecast is available.",
                weather_used=True,
            )
        if "indoor" in state.methods:
            return Advice(
                "recommend",
                "Consider washing now with your indoor-drying option.",
                "Your deadline is urgent, rain conflicts with outdoor drying, and you confirmed "
                "indoor drying is available and suitable.",
                weather_used=True,
            )
        if not state.indoor_checked:
            return Advice(
                "clarify",
                "Is indoor drying available and suitable for these clothes?",
                "Your deadline is urgent, no dryer is declared, and the fictional forecast "
                "expects rain. This missing fact could change the advice.",
                weather_used=True,
            )
        return Advice(
            "insufficient_evidence",
            "No declared option supports a reliable deadline plan.",
            "Rain conflicts with outdoor drying; no dryer is declared and indoor drying "
            "has been ruled out.",
            "Check another genuinely available option; I will not invent one.",
            weather_used=True,
        )
    return Advice(
        "recommend",
        "Consider washing now with outdoor drying.",
        "Outdoor drying is declared suitable and the fictional forecast shows no rain in "
        "the relevant window. This is not a drying-time estimate.",
        f"Your {sheltered} option is also available." if sheltered else None,
        weather_used=True,
    )
