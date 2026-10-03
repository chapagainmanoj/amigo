"""Run the synthetic flow preview. No model, network, transcript, or production dependencies."""

import asyncio
import json
import sys
from dataclasses import asdict

from flow_logic import SCENARIOS, FlowState, transition


async def render(state: FlowState, *, clear: bool = True) -> None:
    if clear:
        print("\033[2J\033[H", end="")
    print("SYNTHETIC DESIGN PREVIEW — not CBT treatment or a personal-use version")
    print("Fixed fictional examples only. No AI, network, saved transcript, or Amigo Tools.")
    print("Do not enter personal information. Stop or exit at any time.\n")
    print(json.dumps(asdict(state), indent=2))
    print()
    if state.stage == "notice":
        print("Question: do explicit start, one step at a time, back, and stop feel clear?")
        print("[c] Preview fictional flow (not consent to a personal/research protocol)")
    elif state.stage == "scenario":
        print("Choose a fictional example:")
        for index, scenario in enumerate(SCENARIOS, 1):
            print(f"[{index}] {scenario.title}")
    elif state.stage in {"fact", "interpretation", "takeaway", "done"}:
        scenario = SCENARIOS[state.scenario_index]
        print(scenario.event)
        if state.stage == "fact":
            print("Which sentence is directly described in this fictional event?")
            choices = scenario.fact_choices
        elif state.stage == "interpretation":
            print("Which interpretation preserves uncertainty about this fictional event?")
            choices = scenario.interpretation_choices
        elif state.stage == "takeaway":
            print("Select an optional fictional takeaway, or choose none:")
            choices = scenario.takeaway_choices
        else:
            print("Fictional flow finished. No Task, journal, Memory, or outcome was saved.")
            print(f"Selected: {scenario.takeaway_choices[state.takeaway_choice]}")
            choices = ()
        for index, choice in enumerate(choices, 1):
            print(f"[{index}] {choice}")
    elif state.stage == "stopped":
        print("Preview stopped; selections cleared. No completion requirement.")
    elif state.stage == "exit":
        print("Exited; selections cleared.")
    print("\n[b] Back  [s] Stop and clear  [q] Exit and clear")
    if state.stage in {"done", "stopped"}:
        print("[r] Restart at preview notice")


async def main() -> None:
    state = FlowState()
    if sys.argv[1:] == ["--demo"]:
        await render(state, clear=False)
        for action in ("c", "1", "2", "1", "b", "1", "1", "2", "b", "s", "r", "q"):
            state = await transition(state, action)
            print(f"\n--- Demo menu key: {action} ---")
            await render(state, clear=False)
        return
    if sys.argv[1:]:
        print("Usage: python prototype_cli.py [--demo]")
        return
    while state.stage != "exit":
        await render(state)
        try:
            action = await asyncio.to_thread(input, "Menu key only: ")
        except (EOFError, KeyboardInterrupt):
            action = "q"
        state = await transition(state, action.strip().lower())
    await render(state)


if __name__ == "__main__":
    asyncio.run(main())
