#!/usr/bin/env python3
"""Release CLI: refuse a declared Gate A run that does not cover the revision it is offered for.

The checker lives in ``src/evaluation/gate_a_evidence.py`` because production startup runs it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.gate_a_evidence import (  # noqa: E402
    DEFAULT_EVIDENCE,
    DEFAULT_SUITE,
    check_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Archived full JSON artifact for the last passing Gate A run",
    )
    parser.add_argument(
        "--comparison",
        type=Path,
        help="Generated candidate/baseline comparison with completed human review",
    )
    parser.add_argument("--revision", required=True, help="The exact release Git SHA")
    parser.add_argument("--mode", default="daily")
    parser.add_argument("--model", help="Evaluated candidate model; defaults to the Mode primary")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    args = parser.parse_args()

    if not args.evidence.is_file():
        print(f"FAIL: no declared Gate A run at {args.evidence}")
        return 1
    try:
        evidence_bytes = args.evidence.read_bytes()
        evidence = json.loads(evidence_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        print(f"FAIL: {args.evidence} is not readable JSON: {error}")
        return 1

    for label, path in (("baseline", args.baseline), ("comparison", args.comparison)):
        if path is None or not path.is_file():
            print(f"FAIL: no Gate A {label} artifact at {path}")
            return 1
    try:
        baseline_bytes = args.baseline.read_bytes()
        baseline = json.loads(baseline_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        print(f"FAIL: {args.baseline} is not readable JSON: {error}")
        return 1
    try:
        comparison = json.loads(args.comparison.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        print(f"FAIL: {args.comparison} is not readable JSON: {error}")
        return 1

    errors = check_evidence(
        evidence,
        revision=args.revision,
        root=ROOT,
        suite_path=args.suite.resolve(),
        baseline_evidence=baseline,
        candidate_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
        baseline_sha256=hashlib.sha256(baseline_bytes).hexdigest(),
        comparison=comparison,
        mode_id=args.mode,
        model_name=args.model,
    )
    if errors:
        print(f"FAIL: the declared Gate A run cannot stand for {args.revision}")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"ok: a complete passing Gate A run covers {args.revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
