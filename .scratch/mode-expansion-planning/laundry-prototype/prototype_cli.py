"""THROWAWAY terminal shell for the simulated laundry decision flow."""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, replace

from decision_logic import Scenario, advise

WEATHER = ("clear", "rain", "missing", "stale", "wrong_location", "wrong_window")
URGENCY = ("flexible", "urgent", "unknown")
WINDOW = ("available", "unavailable", "unknown")
PREFERENCE = ("outdoor", "dryer", "indoor", None)


async def render(state: Scenario) -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")
    print("LAUNDRY PROTOTYPE — FICTIONAL WEATHER, NO MODEL, NO SIDE EFFECTS")
    print("Methods mean available AND suitable for these clothes. No drying-time guarantees.")
    print(json.dumps({"scenario": asdict(state), "advice": asdict(await advise(state))}, indent=2))
    print("[o] outdoor  [d] dryer  [i] indoor (toggle options)")
    print("[p] preference  [u] urgency  [t] washing window  [w] weather (cycle)")
    print("[k] indoor ruled-out/unknown  [r] reset  [q] quit — state is never saved")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Print illustrative scenarios and exit")
    args = parser.parse_args()
    if args.demo:
        cases = (
            ("Clear outdoor window", Scenario()),
            ("Rain, flexible, outdoor only", Scenario(weather="rain")),
            ("Rain, dryer available", Scenario(methods=("outdoor", "dryer"), weather="rain")),
            ("Urgent, rain, outdoor only", Scenario(urgency="urgent", weather="rain")),
            (
                "Flexible, rain, indoor available",
                Scenario(
                    methods=("outdoor", "indoor"),
                    weather="rain",
                ),
            ),
            (
                "Urgent, rain, indoor available",
                Scenario(
                    methods=("outdoor", "indoor"),
                    urgency="urgent",
                    weather="rain",
                ),
            ),
            (
                "Urgent, rain, indoor ruled out",
                Scenario(
                    urgency="urgent",
                    weather="rain",
                    indoor_checked=True,
                ),
            ),
            ("Stale forecast", Scenario(weather="stale")),
            (
                "Indoor only, missing forecast",
                Scenario(
                    methods=("indoor",),
                    preferred="indoor",
                    weather="missing",
                ),
            ),
            ("No washing window", Scenario(washing_window="unavailable")),
            ("Unknown urgency", Scenario(urgency="unknown")),
        )
        for label, state in cases:
            print(f"\n--- {label} ---")
            await render(state)
        return

    state = Scenario()
    while True:
        await render(state)
        try:
            key = input("> ").strip().lower()
        except EOFError:
            break
        if key == "q":
            break
        if key == "r":
            state = Scenario()
        elif key in ("o", "d", "i"):
            method = {"o": "outdoor", "d": "dryer", "i": "indoor"}[key]
            methods = tuple(value for value in state.methods if value != method)
            if method not in state.methods:
                methods += (method,)
            state = replace(
                state,
                methods=methods,
                indoor_checked=True if method == "indoor" else state.indoor_checked,
            )
        elif key == "k" and "indoor" not in state.methods:
            state = replace(state, indoor_checked=not state.indoor_checked)
        elif key in ("p", "u", "t", "w"):
            field, values = {
                "p": ("preferred", PREFERENCE),
                "u": ("urgency", URGENCY),
                "t": ("washing_window", WINDOW),
                "w": ("weather", WEATHER),
            }[key]
            current = getattr(state, field)
            state = replace(state, **{field: values[(values.index(current) + 1) % len(values)]})


if __name__ == "__main__":
    asyncio.run(main())
