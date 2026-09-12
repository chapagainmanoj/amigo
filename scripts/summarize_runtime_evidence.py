"""Summarize content-free Store and event-loop measurements from application logs."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from collections.abc import Iterable

DATABASE_PATTERN = re.compile(
    r"database_operation=(?P<operation>[a-z_]+) "
    r"outcome=(?P<outcome>ok|error) duration_ms=(?P<duration>[0-9.]+)"
)
EVENT_LOOP_PATTERN = re.compile(r"event_loop_delay_ms=(?P<duration>[0-9.]+)")


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _distribution(values: list[float]) -> dict:
    return {
        "count": len(values),
        "p50_ms": _nearest_rank(values, 0.50),
        "p95_ms": _nearest_rank(values, 0.95),
        "max_ms": max(values) if values else None,
    }


def summarize(lines: Iterable[str]) -> dict:
    """Extract only timing/outcome fields; participant content is never retained."""
    database_durations: dict[str, list[float]] = defaultdict(list)
    database_errors: dict[str, int] = defaultdict(int)
    event_loop_delays: list[float] = []

    for line in lines:
        if match := DATABASE_PATTERN.search(line):
            operation = match.group("operation")
            database_durations[operation].append(float(match.group("duration")))
            if match.group("outcome") == "error":
                database_errors[operation] += 1
        if match := EVENT_LOOP_PATTERN.search(line):
            event_loop_delays.append(float(match.group("duration")))

    all_database_durations = [
        duration
        for durations in database_durations.values()
        for duration in durations
    ]
    return {
        "database": {
            "overall": _distribution(all_database_durations),
            "operations": {
                operation: {
                    **_distribution(database_durations[operation]),
                    "errors": database_errors[operation],
                }
                for operation in sorted(database_durations)
            },
        },
        "event_loop": _distribution(event_loop_delays),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "log_file",
        nargs="?",
        help="Application log file; reads stdin when omitted.",
    )
    args = parser.parse_args()
    if args.log_file:
        with open(args.log_file, encoding="utf-8") as log_file:
            result = summarize(log_file)
    else:
        result = summarize(sys.stdin)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
