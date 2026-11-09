#!/usr/bin/env python3
"""Evaluate the Build workflow's lane-aware terminal required check."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping


CODE_JOBS = ("backend", "frontend", "security")
INTEGRATION_JOBS = (
    "runtime-authorization",
    "postgres-shards",
    "postgres-coverage",
    "browser",
    "live-workspace",
    "diagram-exports",
    "production-containers",
)
ASSURANCE_JOBS = ("release-codeql", "release-extended")
RELEASE_JOBS = ("publish-containers",)


def _flag(outputs: Mapping[str, object], name: str, errors: list[str]) -> bool:
    value = outputs.get(name)
    if value not in {"true", "false"}:
        errors.append(f"prepare output {name!r} must be 'true' or 'false', got {value!r}")
    return value == "true"


def validate(needs: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    prepare = needs.get("prepare")
    if not isinstance(prepare, Mapping):
        return ["prepare result is missing from the terminal gate"]
    if prepare.get("result") != "success":
        errors.append(f"prepare concluded {prepare.get('result')!r}, expected 'success'")

    outputs = prepare.get("outputs")
    if not isinstance(outputs, Mapping):
        outputs = {}
        errors.append("prepare outputs are missing from the terminal gate")
    code = _flag(outputs, "code", errors)
    integration = _flag(outputs, "integration", errors)
    assurance = _flag(outputs, "assurance", errors)
    release = _flag(outputs, "release", errors)
    lane = outputs.get("lane")

    if lane == "documentation" and (code or integration or assurance or release):
        errors.append("the documentation lane cannot request code, integration, assurance, or release jobs")
    elif lane == "code" and (not code or integration or assurance or release):
        errors.append("the code lane requires code jobs only")
    elif lane == "integration" and (not code or not integration):
        errors.append("the integration lane requires code and integration jobs")
    elif lane not in {"documentation", "code", "integration"}:
        errors.append(f"unknown validation lane {lane!r}")
    if assurance and not integration:
        errors.append("assurance jobs require the integration lane")
    if release and not integration:
        errors.append("release jobs require the integration lane")
    if release and not assurance:
        errors.append("release jobs require assurance jobs")

    expected = {job: code for job in CODE_JOBS}
    expected.update({job: integration for job in INTEGRATION_JOBS})
    expected.update({job: assurance for job in ASSURANCE_JOBS})
    expected.update({job: release for job in RELEASE_JOBS})
    for job, should_succeed in expected.items():
        entry = needs.get(job)
        result = entry.get("result") if isinstance(entry, Mapping) else None
        wanted = "success" if should_succeed else "skipped"
        if result != wanted:
            errors.append(f"{job} concluded {result!r}, expected {wanted!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--needs-json", required=True)
    parser.add_argument("--github-step-summary")
    args = parser.parse_args()
    needs = json.loads(args.needs_json)
    errors = validate(needs)
    lines = ["## Stable validation gate", ""]
    if errors:
        lines.extend(["The selected validation lane did not complete:", ""])
        lines.extend(f"- {error}" for error in errors)
    else:
        lane = needs["prepare"]["outputs"]["lane"]
        lines.append(f"The `{lane}` lane completed with all required jobs successful.")
    summary = "\n".join(lines) + "\n"
    if args.github_step_summary:
        with open(args.github_step_summary, "a", encoding="utf-8") as handle:
            handle.write(summary)
    print(summary, end="")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
