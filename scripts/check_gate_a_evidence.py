#!/usr/bin/env python3
"""Refuse a declared Gate A run that does not cover the revision it is offered for.

Acceptance criterion 6 of issue 14 requires the complete suite to run again whenever an
invalidating model input changes. Recording fingerprints inside the evidence proves nothing on
its own: a stale run can be attached to a new release by hand. This checker recomputes every
fingerprint from the working tree and rejects the evidence unless the recorded run really is a
complete, passing, three-repetition run of the approved suite against these exact inputs.

It is fail-closed: a missing, unreadable, partial, aborted, or dev-scoped run is a failure, and
so is an absent evidence file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402
from src.evaluation.gate_a import (  # noqa: E402
    PROMPT_SOURCE,
    THRESHOLDS,
    TIME_BEHAVIOR_SOURCES,
    TURN_CONTEXT_SOURCES,
    VALIDATOR_SOURCE,
    canonical_hash,
    file_set_hash,
    invalidating_inputs,
    load_suite,
    summarize_scores,
    tool_schema,
)

DEFAULT_SUITE = ROOT / "evals/gate_a/v1/cases.json"
DEFAULT_EVIDENCE = ROOT / "evidence/gate-a/latest.json"
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_REPETITIONS = 3


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_fingerprints(root: Path, suite_path: Path) -> dict[str, str]:
    """Recompute every invalidating fingerprint from the tree as it stands now."""
    return {
        "prompt_source_sha256": _sha256(root / PROMPT_SOURCE),
        "validator_source_sha256": _sha256(root / VALIDATOR_SOURCE),
        "turn_context_source_sha256": file_set_hash(
            [root / relative for relative in TURN_CONTEXT_SOURCES], root
        ),
        "time_behavior_source_sha256": file_set_hash(
            [root / relative for relative in TIME_BEHAVIOR_SOURCES], root
        ),
        "all_invalidating_inputs_sha256": file_set_hash(invalidating_inputs(root), root),
        "case_set_sha256": _sha256(suite_path),
        "tool_schema_sha256": canonical_hash(tool_schema()),
    }


def check_evidence(
    evidence: object,
    *,
    revision: str,
    root: Path = ROOT,
    suite_path: Path = DEFAULT_SUITE,
) -> list[str]:
    """Return every reason this evidence cannot stand for ``revision``; empty means it can."""
    errors: list[str] = []
    if not isinstance(evidence, dict):
        return ["Gate A evidence must be a JSON object"]
    if not REVISION_PATTERN.fullmatch(revision):
        errors.append("revision must be a full lowercase Git commit SHA")

    suite = load_suite(suite_path)
    if evidence.get("suite_id") != suite.suite_id:
        errors.append(f"evidence.suite_id must be {suite.suite_id}")
    if evidence.get("status") != "passed" or evidence.get("passed") is not True:
        errors.append(f"the declared run did not pass: status={evidence.get('status')!r}")
    if evidence.get("repetitions") is not REQUIRED_REPETITIONS:
        errors.append("a declared run must use exactly three repetitions")
    if evidence.get("provider_incidents"):
        errors.append("the declared run recorded a provider incident and is not release evidence")
    if not evidence.get("completed_at"):
        errors.append("evidence.completed_at is required")

    expected_ids = sorted(case.id for case in suite.cases)
    if sorted(evidence.get("selected_cases") or []) != expected_ids:
        errors.append("a declared run must select every approved case, not a development subset")

    executions = evidence.get("executions")
    if not isinstance(executions, list):
        errors.append("evidence.executions is required")
        executions = []
    expected_executions = len(expected_ids) * REQUIRED_REPETITIONS
    if len(executions) != expected_executions:
        errors.append(
            f"expected {expected_executions} executions, found {len(executions)}"
        )
    # Repetitions are checked by identity, not by count: three records of repetition 1 is not
    # "every case three times", and a count alone cannot tell the difference.
    repetitions_by_case: dict[object, set] = defaultdict(set)
    scored: list[dict] = []
    for item in executions:
        if not isinstance(item, dict):
            errors.append("every execution must be an object")
            continue
        repetitions_by_case[item.get("case_id")].add(item.get("repetition"))
        # An allowlist, not a denylist: an unrecognised or absent status is not a success.
        if item.get("status") != "completed" or item.get("passed") is not True:
            errors.append(
                f"{item.get('case_id')} repetition {item.get('repetition')} "
                "did not complete and pass"
            )
        if not isinstance(item.get("metric_results"), dict):
            errors.append(
                f"{item.get('case_id')} repetition {item.get('repetition')} "
                "records no metric results"
            )
        else:
            scored.append(item)
    for case_id in expected_ids:
        observed = sorted(str(value) for value in repetitions_by_case.get(case_id, ()))
        if repetitions_by_case.get(case_id) != set(range(1, REQUIRED_REPETITIONS + 1)):
            errors.append(f"{case_id} did not run repetitions 1, 2 and 3 (found {observed})")

    release_inputs = evidence.get("release_inputs")
    if not isinstance(release_inputs, dict):
        errors.append("evidence.release_inputs is required")
        release_inputs = {}
    if release_inputs.get("git_revision") != revision:
        errors.append(
            "the declared run was executed against "
            f"{release_inputs.get('git_revision')!r}, not {revision!r}"
        )
    if release_inputs.get("working_tree_dirty") is not False:
        errors.append("the declared run was executed from a dirty working tree")
    if release_inputs.get("model") != settings.default_model:
        errors.append(
            f"the declared run used model {release_inputs.get('model')!r}, "
            f"not the configured {settings.default_model!r}"
        )

    for name, expected in current_fingerprints(root, suite_path).items():
        recorded = release_inputs.get(name)
        if recorded != expected:
            errors.append(
                f"{name} changed since the declared run "
                f"(recorded {recorded!r}, current {expected!r}); Gate A must run again"
            )

    scores = evidence.get("scores")
    if not isinstance(scores, dict):
        errors.append("evidence.scores is required")
        scores = {}
    for metric in set(scores) - set(THRESHOLDS):
        errors.append(f"scores.{metric} is not an approved Gate A metric")

    # The recorded summary is derived, not trusted: a `passed` flag someone typed is no evidence.
    # Recomputing it from the executions is the only thing that ties the verdict to the run.
    unknown = {
        metric
        for item in scored
        for metric in item["metric_results"]
        if metric not in THRESHOLDS
    }
    if unknown:
        errors.append(f"executions record unapproved metrics: {sorted(unknown)}")
    elif not errors or scored:
        recomputed = summarize_scores(scored, THRESHOLDS)
        if scores != recomputed:
            errors.append("evidence.scores does not match the recorded executions")
        for metric, threshold in THRESHOLDS.items():
            result = recomputed[metric]
            if not result["observations"]:
                errors.append(f"scores.{metric} has no observations")
            elif result["score"] < threshold:
                errors.append(
                    f"scores.{metric} scored {result['score']} "
                    f"below the approved {threshold}"
                )
            if not result["passed"]:
                errors.append(f"scores.{metric} did not meet its approved threshold")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--revision", required=True, help="The exact release Git SHA")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    args = parser.parse_args()

    if not args.evidence.is_file():
        print(f"FAIL: no declared Gate A run at {args.evidence}")
        return 1
    try:
        evidence = json.loads(args.evidence.read_text())
    except json.JSONDecodeError as error:
        print(f"FAIL: {args.evidence} is not readable JSON: {error}")
        return 1

    errors = check_evidence(
        evidence, revision=args.revision, root=ROOT, suite_path=args.suite.resolve()
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
