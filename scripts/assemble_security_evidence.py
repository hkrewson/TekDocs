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
    object_value,
    require,
    validate_evidence_entry,
)


def assemble_evidence(input_directory: Path, candidate_commit: str, *, now: datetime) -> dict[str, Any]:
    require(COMMIT_PATTERN.fullmatch(candidate_commit) is not None, "candidate commit must be an exact lowercase SHA")
    paths = sorted(input_directory.rglob("*.json"))
    require(bool(paths), f"no JSON evidence fragments found in {input_directory}")

    evidence: dict[str, dict[str, Any]] = {}
    for path in paths:
        try:
            raw_record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"could not read evidence fragment {path}: {error}") from error
        record = object_value(raw_record, str(path))
        require(record.get("schema_version") == 1, f"{path} has an unsupported or missing schema_version")
        category, _ = validate_evidence_entry(record, candidate_commit, name=str(path), now=now)
        require(category not in evidence, f"duplicate evidence category: {category}")
        evidence[category] = record

    missing = sorted(REQUIRED_EVIDENCE - evidence.keys())
    require(not missing, f"missing evidence categories: {', '.join(missing)}")
    return {
        "schema_version": 1,
        "candidate_commit": candidate_commit,
        "evidence": [evidence[category] for category in sorted(evidence)],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble a complete, commit-bound TekDocs security evidence set from hosted fragments."
    )
    parser.add_argument("--input-directory", required=True, type=Path)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        assembled = assemble_evidence(args.input_directory, args.candidate_commit, now=datetime.now(UTC))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(assembled, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"Security evidence was not assembled: {error}", file=sys.stderr)
        return 1
    print(f"Assembled {len(assembled['evidence'])} evidence records for {assembled['candidate_commit']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
