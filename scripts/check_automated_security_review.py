from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RECORD = ROOT / ".github" / "automated-security-review.json"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]{2,63}$")
ISSUE_PATTERN = re.compile(r"^#[1-9][0-9]*$")
SEVERITIES = {"critical", "high", "medium", "low", "informational"}
STATUSES = {"open", "resolved", "accepted"}
REQUIRED_EVIDENCE = {
    "authorization_and_rls",
    "backup_and_restore",
    "browser_security",
    "codeql",
    "dast",
    "dependency_license_secret",
    "image_scan",
    "production_images_sbom_provenance",
    "source_review",
    "upgrade",
}
EVIDENCE_FIELDS = {
    "schema_version",
    "category",
    "status",
    "scope_commit",
    "completed_at",
    "tool",
    "tool_version",
    "reference",
    "immutable_identifier",
}
FALSE_PUBLIC_CLAIMS = {
    "independent_human_security_assessment",
    "penetration_test",
    "compliance_audit",
    "certification",
    "independent_assurance",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token)\s*[:=]\s*[^\s,;]{8,}"),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def object_value(value: object, name: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{name} must be an object")
    return value


def list_value(value: object, name: str) -> list[Any]:
    require(isinstance(value, list), f"{name} must be a list")
    return value


def text_value(value: object, name: str, *, maximum: int = 1_000) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{name} is missing")
    require(len(value) <= maximum, f"{name} exceeds {maximum} characters")
    require(
        not any(ord(character) < 32 and character not in "\n\t" for character in value),
        f"{name} contains control characters",
    )
    return value.strip()


def timestamp(value: object, name: str) -> datetime:
    raw = text_value(value, name, maximum=64)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} is invalid") from error
    require(parsed.tzinfo is not None, f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def walk_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in walk_strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in walk_strings(child)]
    return []


def reject_secret_shaped_content(data: dict[str, Any]) -> None:
    for value in walk_strings(data):
        for pattern in SECRET_PATTERNS:
            require(pattern.search(value) is None, "record contains secret-shaped content")


def validate_evidence_entry(
    record: dict[str, Any],
    candidate_commit: str,
    *,
    name: str,
    now: datetime,
) -> tuple[str, datetime]:
    require(record.get("schema_version", 1) == 1, f"{name} has an unsupported schema_version")
    unexpected_fields = sorted(record.keys() - EVIDENCE_FIELDS)
    require(not unexpected_fields, f"{name} contains unsupported fields: {', '.join(unexpected_fields)}")
    category = text_value(record.get("category"), f"{name}.category", maximum=80)
    require(category in REQUIRED_EVIDENCE, f"unknown evidence category: {category}")
    require(record.get("status") == "passed", f"evidence {category} has not passed")
    require(record.get("scope_commit") == candidate_commit, f"evidence {category} does not match candidate commit")
    completed_at = timestamp(record.get("completed_at"), f"evidence {category}.completed_at")
    require(completed_at <= now, f"evidence {category} completion is in the future")
    text_value(record.get("tool"), f"evidence {category}.tool", maximum=160)
    text_value(record.get("tool_version"), f"evidence {category}.tool_version", maximum=160)
    text_value(record.get("reference"), f"evidence {category}.reference", maximum=500)
    text_value(record.get("immutable_identifier"), f"evidence {category}.immutable_identifier", maximum=500)
    reject_secret_shaped_content(record)
    return category, completed_at


def validate_evidence(
    data: dict[str, Any],
    candidate_commit: str,
    *,
    review_completed_at: datetime,
    now: datetime,
) -> None:
    records = list_value(data.get("evidence"), "evidence")
    categories: set[str] = set()
    for index, raw_record in enumerate(records):
        record = object_value(raw_record, f"evidence[{index}]")
        category, completed_at = validate_evidence_entry(
            record,
            candidate_commit,
            name=f"evidence[{index}]",
            now=now,
        )
        require(category not in categories, f"duplicate evidence category: {category}")
        categories.add(category)
        require(completed_at <= review_completed_at, f"evidence {category} postdates review completion")
    missing = sorted(REQUIRED_EVIDENCE - categories)
    require(not missing, f"missing evidence categories: {', '.join(missing)}")


def validate_findings(data: dict[str, Any], now: datetime) -> None:
    identifiers: set[str] = set()
    unresolved_blockers: list[str] = []
    open_findings: list[str] = []
    for index, raw_finding in enumerate(list_value(data.get("findings"), "findings")):
        finding = object_value(raw_finding, f"findings[{index}]")
        identifier = text_value(finding.get("id"), f"findings[{index}].id", maximum=64)
        require(IDENTIFIER_PATTERN.fullmatch(identifier) is not None, f"invalid finding id: {identifier!r}")
        require(identifier not in identifiers, f"duplicate finding id: {identifier}")
        identifiers.add(identifier)
        severity = finding.get("severity")
        status = finding.get("status")
        require(severity in SEVERITIES, f"invalid severity for {identifier}: {severity!r}")
        require(status in STATUSES, f"invalid status for {identifier}: {status!r}")
        text_value(finding.get("title"), f"finding {identifier}.title", maximum=240)
        text_value(finding.get("disposition"), f"finding {identifier}.disposition", maximum=1_500)
        text_value(finding.get("owner"), f"finding {identifier}.owner", maximum=160)
        if status == "resolved":
            evidence = list_value(finding.get("evidence"), f"finding {identifier}.evidence")
            require(bool(evidence), f"resolved finding {identifier} has no remediation evidence")
            for evidence_index, item in enumerate(evidence):
                text_value(item, f"finding {identifier}.evidence[{evidence_index}]", maximum=500)
            text_value(finding.get("retest"), f"finding {identifier}.retest", maximum=500)
        if severity in {"critical", "high"} and status != "resolved":
            unresolved_blockers.append(identifier)
        if status == "open":
            open_findings.append(identifier)
        if status == "accepted":
            require(severity not in {"critical", "high"}, f"release-blocking finding cannot be accepted: {identifier}")
            acceptance = object_value(finding.get("acceptance"), f"finding {identifier}.acceptance")
            text_value(acceptance.get("rationale"), f"finding {identifier}.acceptance.rationale", maximum=1_000)
            text_value(acceptance.get("mitigation"), f"finding {identifier}.acceptance.mitigation", maximum=1_000)
            owner_issue = text_value(
                acceptance.get("owner_issue"),
                f"finding {identifier}.acceptance.owner_issue",
                maximum=32,
            )
            require(
                ISSUE_PATTERN.fullmatch(owner_issue) is not None,
                f"finding {identifier} has an invalid owner issue",
            )
            review_at = timestamp(acceptance.get("review_at"), f"finding {identifier}.acceptance.review_at")
            require(review_at > now, f"finding {identifier} acceptance review is expired")
    require(not unresolved_blockers, f"unresolved Critical/High findings: {', '.join(unresolved_blockers)}")
    require(not open_findings, f"findings without a release disposition: {', '.join(open_findings)}")


def validate_exceptions(data: dict[str, Any], now: datetime) -> None:
    identifiers: set[str] = set()
    for index, raw_exception in enumerate(list_value(data.get("exceptions"), "exceptions")):
        exception = object_value(raw_exception, f"exceptions[{index}]")
        identifier = text_value(exception.get("id"), f"exceptions[{index}].id", maximum=64)
        require(IDENTIFIER_PATTERN.fullmatch(identifier) is not None, f"invalid exception id: {identifier!r}")
        require(identifier not in identifiers, f"duplicate exception id: {identifier}")
        identifiers.add(identifier)
        text_value(exception.get("scanner"), f"exception {identifier}.scanner", maximum=120)
        dependency = text_value(exception.get("dependency"), f"exception {identifier}.dependency", maximum=200)
        require(dependency not in {"*", "all", "global"}, f"exception {identifier} is not dependency-specific")
        text_value(exception.get("advisory"), f"exception {identifier}.advisory", maximum=160)
        text_value(exception.get("rationale"), f"exception {identifier}.rationale", maximum=1_000)
        owner_issue = text_value(exception.get("owner_issue"), f"exception {identifier}.owner_issue", maximum=32)
        require(ISSUE_PATTERN.fullmatch(owner_issue) is not None, f"exception {identifier} has an invalid owner issue")
        expires_at = timestamp(exception.get("expires_at"), f"exception {identifier}.expires_at")
        require(expires_at > now, f"exception {identifier} is expired")


def validate_public_claims(data: dict[str, Any]) -> None:
    claims = object_value(data.get("public_claims"), "public_claims")
    for claim in FALSE_PUBLIC_CLAIMS:
        require(claim in claims, f"public claim is missing: {claim}")
        require(claims[claim] is False, f"public claim must remain false: {claim}")
    statement = text_value(claims.get("statement"), "public_claims.statement", maximum=1_000).lower()
    for phrase in ("not received", "independent human security assessment", "automated", "tested scope"):
        require(phrase in statement, f"public limitation statement must include: {phrase}")


def validate_record(data: dict[str, Any], *, candidate_commit: str, now: datetime | None = None) -> None:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    require(
        COMMIT_PATTERN.fullmatch(candidate_commit) is not None,
        "candidate commit must be an exact 40-character lowercase SHA",
    )
    require(data.get("schema_version") == 1, "unsupported or missing schema_version")
    require(data.get("status") == "complete", "automated security review status is not complete")
    record_commit = data.get("candidate_commit")
    require(
        isinstance(record_commit, str) and COMMIT_PATTERN.fullmatch(record_commit) is not None,
        "record candidate_commit is missing or invalid",
    )
    require(
        record_commit == candidate_commit,
        f"stale review scope: record covers {record_commit}, candidate is {candidate_commit}",
    )
    completed_at = timestamp(data.get("completed_at"), "completed_at")
    require(completed_at <= now, "completed_at cannot be in the future")
    reviewer = object_value(data.get("reviewer"), "reviewer")
    require(
        reviewer.get("kind") == "automated_or_ai_assisted",
        "reviewer.kind must disclose automated or AI-assisted review",
    )
    for field in ("name", "version", "operator", "method"):
        text_value(reviewer.get(field), f"reviewer.{field}", maximum=1_000)
    limitations = list_value(reviewer.get("limitations"), "reviewer.limitations")
    require(bool(limitations), "reviewer.limitations must not be empty")
    for index, limitation in enumerate(limitations):
        text_value(limitation, f"reviewer.limitations[{index}]", maximum=1_000)
    text_value(data.get("private_report_reference"), "private_report_reference", maximum=500)
    validate_evidence(data, candidate_commit, review_completed_at=completed_at, now=now)
    validate_findings(data, now)
    validate_exceptions(data, now)
    validate_public_claims(data)
    reject_secret_shaped_content(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the value-minimized automated security review for a frozen candidate commit."
    )
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--candidate-commit", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate_commit = args.candidate_commit
    try:
        data = json.loads(args.record.read_text(encoding="utf-8"))
        require(isinstance(data, dict), "review record must be a JSON object")
        validate_record(data, candidate_commit=candidate_commit)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Automated security review gate blocked: {error}", file=sys.stderr)
        return 1
    print(f"Automated security review gate passed for {candidate_commit} with {len(data['findings'])} findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
