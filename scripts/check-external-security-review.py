from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / ".github" / "external-security-review.json"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FINDING_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]{2,40}$")
SEVERITIES = {"critical", "high", "medium", "low", "informational"}
STATUSES = {"open", "resolved", "accepted"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate() -> None:
    data = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(data.get("status") == "complete", "automated review status is not complete")
    require(isinstance(data.get("reviewer"), str) and data["reviewer"].strip(), "reviewer identity is missing")
    require(isinstance(data.get("scope_commit"), str) and COMMIT_PATTERN.fullmatch(data["scope_commit"]), "exact 40-character scope commit is missing")
    require(isinstance(data.get("report_reference"), str) and data["report_reference"].strip(), "value-free report reference is missing")
    try:
        completed_at = datetime.fromisoformat(str(data.get("completed_at")).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("review completion timestamp is invalid") from error
    require(completed_at.tzinfo is not None, "review completion timestamp must include a timezone")

    findings = data.get("findings")
    require(isinstance(findings, list), "findings must be a list")
    identifiers: set[str] = set()
    unresolved_blockers: list[str] = []
    for finding in findings:
        identifier = finding.get("id")
        require(isinstance(identifier, str) and FINDING_ID_PATTERN.fullmatch(identifier), f"invalid finding id: {identifier!r}")
        require(identifier not in identifiers, f"duplicate finding id: {identifier}")
        identifiers.add(identifier)
        severity = finding.get("severity")
        status = finding.get("status")
        require(severity in SEVERITIES, f"invalid severity for {identifier}: {severity!r}")
        require(status in STATUSES, f"invalid status for {identifier}: {status!r}")
        require(isinstance(finding.get("title"), str) and finding["title"].strip(), f"missing title for {identifier}")
        require(isinstance(finding.get("disposition"), str) and finding["disposition"].strip(), f"missing disposition for {identifier}")
        require(isinstance(finding.get("evidence"), list) and finding["evidence"], f"missing remediation evidence for {identifier}")
        if severity in {"critical", "high"} and status != "resolved":
            unresolved_blockers.append(identifier)
        if status == "accepted":
            require(severity not in {"critical", "high"}, f"release-blocking finding cannot be accepted: {identifier}")

    require(not unresolved_blockers, f"unresolved Critical/High findings: {unresolved_blockers}")
    print(f"Automated security review gate passed for {data['scope_commit']} with {len(findings)} triaged findings.")


def main() -> int:
    try:
        validate()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Automated security review gate blocked: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
