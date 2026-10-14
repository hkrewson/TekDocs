"""Compact read-only CI failure inventory; raw logs are deliberately excluded."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from release_status import ROOT, gh_json


def summarize(run: dict, jobs: list[dict], ledger: dict) -> dict:
    failures = []
    for job in jobs:
        if job.get("conclusion") not in {
            "failure",
            "timed_out",
            "cancelled",
            "action_required",
        }:
            continue
        matches = [
            entry
            for entry in ledger["failures"]
            if entry["run_id"] == run["id"] and entry["job"] == job["name"]
        ]
        tracked = bool(
            matches
            and all(
                matches[0].get(key)
                for key in ("owner", "reproduction", "cause", "next_action")
            )
        )
        failures.append(
            {
                "job": job["name"],
                "conclusion": job["conclusion"],
                "owner": matches[0]["owner"] if tracked else ledger["default_owner"],
                "triage": "tracked" if tracked else "required",
            }
        )
    return {
        "run_id": run["id"],
        "candidate": run["head_sha"],
        "status": run["status"],
        "conclusion": run.get("conclusion"),
        "failures": failures,
        "next": (
            "Reproduce the named failures; retain useful running jobs. Full validation remains required on the final candidate."
            if failures
            else "No failed jobs observed; unfinished jobs are not passes."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--repository", default="hkrewson/TekDocs")
    parser.add_argument(
        "--ledger",
        type=Path,
        default=ROOT / "planning/releases/validation-failures.json",
    )
    args = parser.parse_args()
    try:
        if args.run_id <= 0 or not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository
        ):
            raise ValueError("invalid run scope")
        prefix = f"repos/{args.repository}/actions/runs/{args.run_id}"
        run = gh_json(prefix)
        jobs, page = [], 1
        while True:
            batch = gh_json(f"{prefix}/jobs?per_page=100&page={page}")["jobs"]
            jobs.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        result = summarize(run, jobs, json.loads(args.ledger.read_text()))
        print(json.dumps(result, indent=2))
        return int(
            bool(result["failures"])
            or run["status"] != "completed"
            or run.get("conclusion") != "success"
        )
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        print("CI status unavailable; no successful result inferred.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
