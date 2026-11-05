#!/usr/bin/env python3
"""Decide whether a scheduled assurance workflow needs expensive work."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone


def should_run(
    *,
    event_name: str,
    current_sha: str,
    prior_sha: str | None,
    prior_conclusion: str | None,
    now: datetime,
) -> tuple[bool, str]:
    if event_name != "schedule":
        return True, f"{event_name} runs are never deduplicated"
    if not prior_sha or not prior_conclusion:
        return True, "no prior scheduled run was found"
    if prior_sha != current_sha:
        return True, "main has changed since the prior scheduled run"
    if prior_conclusion != "success":
        return True, f"the prior scheduled run concluded {prior_conclusion}"
    if now.day <= 7:
        return True, "the unchanged commit is due for its monthly refresh"
    return False, "the same commit already has successful scheduled assurance this month"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--current-sha", required=True)
    parser.add_argument("--prior-sha")
    parser.add_argument("--prior-conclusion")
    parser.add_argument("--github-output")
    args = parser.parse_args()

    run, reason = should_run(
        event_name=args.event_name,
        current_sha=args.current_sha,
        prior_sha=args.prior_sha,
        prior_conclusion=args.prior_conclusion,
        now=datetime.now(timezone.utc),
    )
    output = f"run={'true' if run else 'false'}\nreason={reason}\n"
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write(output)
    print(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
