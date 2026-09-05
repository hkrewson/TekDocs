from __future__ import annotations

import copy
import importlib.util
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "check_automated_security_review.py"
SPEC = importlib.util.spec_from_file_location("check_automated_security_review", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the automated security review validator")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CANDIDATE = "a" * 40
NOW = datetime(2026, 9, 4, tzinfo=UTC)


def valid_record() -> dict[str, object]:
    evidence = [
        {
            "category": category,
            "status": "passed",
            "scope_commit": CANDIDATE,
            "completed_at": "2026-09-03T18:00:00Z",
            "tool": f"TekDocs {category} gate",
            "tool_version": "1",
            "reference": f"https://github.com/example/project/actions/runs/100#{category}",
            "immutable_identifier": f"run-100:{category}",
        }
        for category in sorted(MODULE.REQUIRED_EVIDENCE)
    ]
    return {
        "schema_version": 1,
        "status": "complete",
        "candidate_commit": CANDIDATE,
        "completed_at": "2026-09-03T19:00:00Z",
        "reviewer": {
            "kind": "automated_or_ai_assisted",
            "name": "Example review tool",
            "version": "2026.09",
            "operator": "Project maintainer",
            "method": "Threat-model-guided source review followed by focused retesting.",
            "limitations": ["The review cannot prove the absence of defects."],
        },
        "private_report_reference": "Private report retained by the project maintainer: review-100",
        "evidence": evidence,
        "findings": [
            {
                "id": "TD-TEST-001",
                "severity": "medium",
                "status": "resolved",
                "title": "Example bounded finding",
                "disposition": "The affected boundary was corrected and retested.",
                "owner": "Project maintainer",
                "evidence": ["tests/example.py::test_regression"],
                "retest": "Hosted run 100, focused regression",
            }
        ],
        "exceptions": [],
        "public_claims": {
            "independent_human_security_assessment": False,
            "penetration_test": False,
            "compliance_audit": False,
            "certification": False,
            "independent_assurance": False,
            "statement": (
                "TekDocs has not received an independent human security assessment. "
                "Automated checks provide evidence only for their tested scope."
            ),
        },
    }


class AutomatedSecurityReviewValidationTests(unittest.TestCase):
    def assert_invalid(self, record: dict[str, object], message: str, *, candidate: str = CANDIDATE) -> None:
        with self.assertRaisesRegex(ValueError, message):
            MODULE.validate_record(record, candidate_commit=candidate, now=NOW)

    def test_complete_record_passes(self) -> None:
        MODULE.validate_record(valid_record(), candidate_commit=CANDIDATE, now=NOW)

    def test_malformed_or_missing_metadata_is_rejected(self) -> None:
        record = valid_record()
        del record["schema_version"]
        self.assert_invalid(record, "schema_version")

    def test_duplicate_finding_id_is_rejected(self) -> None:
        record = valid_record()
        findings = cast(list[object], record["findings"])
        findings.append(copy.deepcopy(findings[0]))
        self.assert_invalid(record, "duplicate finding id")

    def test_unresolved_high_finding_is_rejected(self) -> None:
        record = valid_record()
        finding = record["findings"][0]  # type: ignore[index]
        finding["severity"] = "high"
        finding["status"] = "open"
        self.assert_invalid(record, "unresolved Critical/High")

    def test_accepted_high_finding_is_rejected(self) -> None:
        record = valid_record()
        finding = record["findings"][0]  # type: ignore[index]
        finding["severity"] = "high"
        finding["status"] = "accepted"
        self.assert_invalid(record, "release-blocking finding cannot be accepted")

    def test_expired_exception_is_rejected(self) -> None:
        record = valid_record()
        record["exceptions"] = [
            {
                "id": "TD-EXCEPTION-001",
                "scanner": "Example scanner",
                "dependency": "example-package@1.0",
                "advisory": "CVE-2026-0001",
                "rationale": "The affected code path is not shipped.",
                "owner_issue": "#123",
                "expires_at": "2026-09-03T00:00:00Z",
            }
        ]
        self.assert_invalid(record, "expired")

    def test_stale_candidate_commit_is_rejected(self) -> None:
        self.assert_invalid(valid_record(), "stale review scope", candidate="b" * 40)

    def test_missing_evidence_category_is_rejected(self) -> None:
        record = valid_record()
        evidence = cast(list[dict[str, object]], record["evidence"])
        evidence.pop()
        self.assert_invalid(record, "missing evidence categories")

    def test_mixed_commit_evidence_is_rejected(self) -> None:
        record = valid_record()
        evidence = cast(list[dict[str, object]], record["evidence"])
        evidence[0]["scope_commit"] = "b" * 40
        self.assert_invalid(record, "does not match candidate commit")

    def test_open_medium_finding_is_rejected(self) -> None:
        record = valid_record()
        finding = record["findings"][0]  # type: ignore[index]
        finding["status"] = "open"
        self.assert_invalid(record, "without a release disposition")

    def test_secret_shaped_content_is_rejected(self) -> None:
        record = valid_record()
        record["private_report_reference"] = "access_token=not-a-real-but-secret-shaped-token"
        self.assert_invalid(record, "secret-shaped content")

    def test_accepted_medium_requires_current_owned_follow_up(self) -> None:
        record = valid_record()
        finding = record["findings"][0]  # type: ignore[index]
        finding["status"] = "accepted"
        finding["acceptance"] = {
            "rationale": "The remaining exposure is bounded.",
            "mitigation": "The feature stays disabled by default.",
            "owner_issue": "#123",
            "review_at": "2026-10-01T00:00:00Z",
        }
        MODULE.validate_record(record, candidate_commit=CANDIDATE, now=NOW)


if __name__ == "__main__":
    unittest.main()
