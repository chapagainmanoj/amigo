"""Synthetic research runner; stdout contains fictional fixtures only, never personal content."""

import argparse
import asyncio
import json
from dataclasses import asdict

from research_engine import FIXTURES, VERSION, ResearchEngine


async def run(fixture_id: str, strategy: str, interactive: bool) -> str:
    engine = ResearchEngine()
    state = await engine.start(fixture_id, strategy)
    print(f"\n{VERSION}: {fixture_id} / {strategy}")
    print(FIXTURES[fixture_id].event)
    while state.status == "asking":
        print(json.dumps(asdict(state), indent=2))
        print(f"\nQuestion: {await engine.question(state)}")
        action = "answer"
        if interactive:
            try:
                key = await asyncio.to_thread(
                    input, "[n] Use fictional answer  [k] Skip  [q] Stop: "
                )
            except (EOFError, KeyboardInterrupt):
                key = "q"
            action = {"n": "answer", "k": "skip", "q": "stop"}.get(key.strip().lower(), "invalid")
        if action == "answer":
            print(f"Scripted fictional answer: {await engine.scripted_answer(state)}")
        elif action == "invalid":
            print("Menu keys only; no personal text accepted.")
        state = await engine.advance(state, action)
    print(json.dumps(asdict(state), indent=2))
    return state.status


async def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic-only MVP, not reviewed clinical CBT.")
    parser.add_argument("--case", choices=FIXTURES, default="meeting")
    parser.add_argument("--strategy", choices=("fixed", "adaptive", "compare"), default="compare")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    print("PROVISIONAL RESEARCH MVP — no personal input, model/API, transcript, or Amigo Tools.")
    print("One fictional situation per run; questions/takeaway optional. No expert validation.")
    if args.interactive:
        print("Do not paste personal text: terminal echo/scrollback is not a private surface.")
    strategies = ("fixed", "adaptive") if args.strategy == "compare" else (args.strategy,)
    for strategy in strategies:
        if args.interactive:
            try:
                key = await asyncio.to_thread(
                    input, f"[c] Explicitly start {args.case}/{strategy}  [q] Exit: "
                )
            except (EOFError, KeyboardInterrupt):
                return
            if key.strip().lower() != "c":
                return
        status = await run(args.case, strategy, args.interactive)
        if status == "stopped":
            return


if __name__ == "__main__":
    asyncio.run(main())
