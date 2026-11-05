#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import sys


@dataclass(frozen=True)
class CILane:
    lane: str
    code: bool
    integration: bool


def _is_documentation(path: str) -> bool:
    candidate = PurePosixPath(path.strip())
    if not candidate.parts:
        return False
    return candidate.suffix.lower() == ".md" or candidate.parts[0] in {"docs", "planning"}


def classify(event: str, paths: list[str]) -> CILane:
    changed = [path.strip() for path in paths if path.strip()]
    if event == "workflow_dispatch" or not changed:
        return CILane(lane="integration", code=True, integration=True)
    if all(_is_documentation(path) for path in changed):
        return CILane(lane="documentation", code=False, integration=False)
    if event == "pull_request":
        return CILane(lane="pull-request", code=True, integration=False)
    return CILane(lane="integration", code=True, integration=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a TekDocs GitHub Actions validation lane")
    parser.add_argument("--event", required=True, choices=("pull_request", "push", "workflow_dispatch"))
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    decision = classify(args.event, sys.stdin.read().splitlines())
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"lane={decision.lane}\n")
        output.write(f"code={'true' if decision.code else 'false'}\n")
        output.write(f"integration={'true' if decision.integration else 'false'}\n")
    print(
        f"CI lane: {decision.lane}; code={'yes' if decision.code else 'no'}; "
        f"integration={'yes' if decision.integration else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
