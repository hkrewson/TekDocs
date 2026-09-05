from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from check_automated_security_review import (
    COMMIT_PATTERN,
    REQUIRED_EVIDENCE,
    reject_secret_shaped_content,
    require,
    text_value,
    timestamp,
)


def build_evidence(
    *,
    category: str,
    scope_commit: str,
    tool: str,
    tool_version: str,
    reference: str,
    immutable_identifier: str,
    completed_at: str,
) -> dict[str, Any]:
    require(category in REQUIRED_EVIDENCE, f"unknown evidence category: {category}")
    require(COMMIT_PATTERN.fullmatch(scope_commit) is not None, "scope commit must be an exact lowercase SHA")
    record = {
        "schema_version": 1,
        "category": category,
        "status": "passed",
        "scope_commit": scope_commit,
        "completed_at": timestamp(completed_at, "completed_at").isoformat().replace("+00:00", "Z"),
        "tool": text_value(tool, "tool", maximum=160),
        "tool_version": text_value(tool_version, "tool_version", maximum=160),
        "reference": text_value(reference, "reference", maximum=500),
        "immutable_identifier": text_value(immutable_identifier, "immutable_identifier", maximum=500),
    }
    reject_secret_shaped_content(record)
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write one value-safe, commit-bound TekDocs security evidence record.")
    parser.add_argument("--category", required=True, choices=sorted(REQUIRED_EVIDENCE))
    parser.add_argument("--scope-commit", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--tool-version", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--immutable-identifier", required=True)
    parser.add_argument("--completed-at", default=None)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        record = build_evidence(
            category=args.category,
            scope_commit=args.scope_commit,
            tool=args.tool,
            tool_version=args.tool_version,
            reference=args.reference,
            immutable_identifier=args.immutable_identifier,
            completed_at=args.completed_at or datetime.now(UTC).isoformat(),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"Security evidence was not written: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {record['category']} evidence for {record['scope_commit']} to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
