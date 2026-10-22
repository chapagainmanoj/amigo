"""Synthetic research runner; stdout contains fictional fixtures only, never personal content."""

import argparse
import asyncio
import json
import os
from dataclasses import asdict

from research_engine import FIXTURES, VERSION, ResearchEngine


async def run(
    fixture_id: str,
    strategy: str,
    interactive: bool,
    model: str = "scripted",
    final_eval: bool = False,
) -> str:
    provider = None
    if model != "scripted":
        from model_selector import build_selector

        provider = await build_selector(
            model,
            final_eval=final_eval,
            api_key=os.environ.get("GOOGLE_API_KEY", ""),
        )
    engine = ResearchEngine(provider)
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
    parser.add_argument(
        "--model",
        default="scripted",
        help="scripted, claude-cli:sonnet, ollama:qwen3.5:4b, gemini-3.5-flash",
    )
    parser.add_argument("--final-eval", action="store_true")
    args = parser.parse_args()
    print("PROVISIONAL RESEARCH MVP — fictional input only; no transcripts or Amigo Tools.")
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
        status = await run(args.case, strategy, args.interactive, args.model, args.final_eval)
        if status == "stopped":
            return


if __name__ == "__main__":
    asyncio.run(main())
