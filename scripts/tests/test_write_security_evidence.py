from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "write_security_evidence.py"
SPEC = importlib.util.spec_from_file_location("write_security_evidence", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the security evidence writer")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CANDIDATE = "a" * 40


def build(**overrides: str) -> dict[str, object]:
    values = {
        "category": "dast",
        "scope_commit": CANDIDATE,
        "tool": "OWASP ZAP baseline",
        "tool_version": "sha256:abc123",
        "reference": "https://github.com/example/project/actions/runs/100",
        "immutable_identifier": "run-100:attempt-1:dast",
        "completed_at": "2026-09-04T12:00:00Z",
    }
    values.update(overrides)
    return MODULE.build_evidence(**values)


class SecurityEvidenceWriterTests(unittest.TestCase):
    def test_writes_only_the_bounded_evidence_contract(self) -> None:
        record = build()
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["status"], "passed")
        self.assertEqual(record["scope_commit"], CANDIDATE)
        self.assertEqual(record["completed_at"], "2026-09-04T12:00:00Z")

    def test_rejects_unknown_category_and_invalid_commit(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown evidence category"):
            build(category="performance")
        with self.assertRaisesRegex(ValueError, "exact lowercase SHA"):
            build(scope_commit="abc123")

    def test_rejects_secret_shaped_metadata(self) -> None:
        with self.assertRaisesRegex(ValueError, "secret-shaped content"):
            build(reference="api_key=not-a-real-but-secret-shaped-value")


if __name__ == "__main__":
    unittest.main()
