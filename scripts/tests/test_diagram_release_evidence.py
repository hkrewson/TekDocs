from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "diagram_release_evidence.py"
SPEC = importlib.util.spec_from_file_location("diagram_release_evidence", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the diagram release evidence module")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CANDIDATE = "a" * 40
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def fragment(category: str) -> dict[str, object]:
    identifier = "sha256:" + "b" * 64 if category in {"dependency_contract", "supply_chain"} else f"run-100:{category}"
    return MODULE.build_evidence(
        category=category,
        scope_commit=CANDIDATE,
        tool=f"TekDocs {category} gate",
        tool_version="0.8.46",
        reference=f"https://github.com/example/project/actions/runs/100#{category}",
        immutable_identifier=identifier,
        completed_at="2026-09-05T11:00:00Z",
    )


def write_fragments(directory: Path) -> None:
    for category in MODULE.REQUIRED_CATEGORIES:
        (directory / f"{category}.json").write_text(json.dumps(fragment(category)), encoding="utf-8")


class DiagramReleaseEvidenceTests(unittest.TestCase):
    def test_assembles_complete_sorted_candidate_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_fragments(directory)
            result = MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["candidate_commit"], CANDIDATE)
        self.assertEqual(result["covered_checks"], sorted(MODULE.ALL_REQUIRED_CHECKS))
        self.assertEqual(
            [record["category"] for record in result["evidence"]],
            sorted(MODULE.REQUIRED_CATEGORIES),
        )

    def test_rejects_missing_duplicate_and_mixed_candidate_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_fragments(directory)
            (directory / "production_image.json").unlink()
            with self.assertRaisesRegex(ValueError, "missing diagram evidence categories: production_image"):
                MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)

            duplicate = fragment("browser_accessibility")
            (directory / "duplicate.json").write_text(json.dumps(duplicate), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate diagram evidence category"):
                MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)

            (directory / "duplicate.json").unlink()
            wrong = fragment("production_image")
            wrong["scope_commit"] = "c" * 40
            (directory / "production_image.json").write_text(json.dumps(wrong), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match candidate commit"):
                MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)

    def test_rejects_missing_unknown_or_duplicate_checks(self) -> None:
        evidence = fragment("authoring_and_failures")
        evidence["checks"].pop()
        with self.assertRaisesRegex(ValueError, "is missing checks"):
            MODULE.validate_evidence_entry(evidence, CANDIDATE, name="test", now=NOW)

        evidence = fragment("authoring_and_failures")
        evidence["checks"].append("invented_claim")
        with self.assertRaisesRegex(ValueError, "unknown checks"):
            MODULE.validate_evidence_entry(evidence, CANDIDATE, name="test", now=NOW)

        evidence = fragment("authoring_and_failures")
        evidence["checks"].append(evidence["checks"][0])
        with self.assertRaisesRegex(ValueError, "duplicate checks"):
            MODULE.validate_evidence_entry(evidence, CANDIDATE, name="test", now=NOW)

    def test_rejects_failed_unbounded_future_or_secret_bearing_evidence(self) -> None:
        failed = fragment("browser_accessibility")
        failed["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "has not passed"):
            MODULE.validate_evidence_entry(failed, CANDIDATE, name="test", now=NOW)

        unbounded = fragment("browser_accessibility")
        unbounded["raw_report"] = "raw browser output"
        with self.assertRaisesRegex(ValueError, "unsupported fields: raw_report"):
            MODULE.validate_evidence_entry(unbounded, CANDIDATE, name="test", now=NOW)

        future = fragment("browser_accessibility")
        future["completed_at"] = "2026-09-05T13:00:00Z"
        with self.assertRaisesRegex(ValueError, "completion is in the future"):
            MODULE.validate_evidence_entry(future, CANDIDATE, name="test", now=NOW)

        secret = fragment("browser_accessibility")
        secret["reference"] = "password=definitely-secret-shaped"
        with self.assertRaisesRegex(ValueError, "secret-shaped content"):
            MODULE.validate_evidence_entry(secret, CANDIDATE, name="test", now=NOW)

    def test_digest_categories_require_sha256_identifiers(self) -> None:
        for category in ("dependency_contract", "supply_chain"):
            with self.subTest(category=category), self.assertRaisesRegex(ValueError, "sha256 digest"):
                MODULE.build_evidence(
                    category=category,
                    scope_commit=CANDIDATE,
                    tool="gate",
                    tool_version="1",
                    reference="https://example.invalid/run/1",
                    immutable_identifier="run-1",
                    completed_at="2026-09-05T11:00:00Z",
                )

    def test_rejects_tampered_category_check_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_fragments(directory)
            path = directory / "renderer_and_exports.json"
            altered = copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))
            altered["checks"] = ["deterministic_svg_and_png"]
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "is missing checks"):
                MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)


if __name__ == "__main__":
    unittest.main()
