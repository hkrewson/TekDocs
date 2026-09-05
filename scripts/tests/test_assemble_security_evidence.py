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
MODULE_PATH = SCRIPTS / "assemble_security_evidence.py"
SPEC = importlib.util.spec_from_file_location("assemble_security_evidence", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the security evidence assembler")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CANDIDATE = "a" * 40
NOW = datetime(2026, 9, 4, 13, 0, tzinfo=UTC)


def fragment(category: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "category": category,
        "status": "passed",
        "scope_commit": CANDIDATE,
        "completed_at": "2026-09-04T12:00:00Z",
        "tool": f"TekDocs {category} gate",
        "tool_version": "1",
        "reference": f"https://github.com/example/project/actions/runs/100#{category}",
        "immutable_identifier": f"run-100:{category}",
    }


def write_fragments(directory: Path) -> None:
    for category in MODULE.REQUIRED_EVIDENCE:
        (directory / f"{category}.json").write_text(json.dumps(fragment(category)), encoding="utf-8")


class SecurityEvidenceAssemblerTests(unittest.TestCase):
    def test_assembles_one_sorted_record_per_required_category(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_fragments(directory)
            result = MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)

        self.assertEqual(result["candidate_commit"], CANDIDATE)
        categories = [record["category"] for record in result["evidence"]]
        self.assertEqual(categories, sorted(MODULE.REQUIRED_EVIDENCE))

    def test_rejects_missing_duplicate_and_mixed_commit_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_fragments(directory)
            (directory / "upgrade.json").unlink()
            with self.assertRaisesRegex(ValueError, "missing evidence categories: upgrade"):
                MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)

            duplicate = copy.deepcopy(fragment("dast"))
            (directory / "duplicate.json").write_text(json.dumps(duplicate), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate evidence category: dast"):
                MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)

            (directory / "duplicate.json").unlink()
            wrong_commit = fragment("upgrade")
            wrong_commit["scope_commit"] = "b" * 40
            (directory / "upgrade.json").write_text(json.dumps(wrong_commit), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match candidate commit"):
                MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)

    def test_rejects_unversioned_or_unbounded_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_fragments(directory)
            unversioned = fragment("dast")
            del unversioned["schema_version"]
            (directory / "dast.json").write_text(json.dumps(unversioned), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing schema_version"):
                MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)

            unbounded = fragment("dast")
            unbounded["raw_report"] = "scanner output does not belong in the public fragment"
            (directory / "dast.json").write_text(json.dumps(unbounded), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported fields: raw_report"):
                MODULE.assemble_evidence(directory, CANDIDATE, now=NOW)


if __name__ == "__main__":
    unittest.main()
