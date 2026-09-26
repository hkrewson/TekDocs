from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "check-responsive-acceptance.py"
SPEC = importlib.util.spec_from_file_location("check_responsive_acceptance", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the responsive acceptance module")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ResponsiveAcceptanceTests(unittest.TestCase):
    def temporary_json(self, source: Path, transform) -> Path:
        value = json.loads(source.read_text(encoding="utf-8"))
        transform(value)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / source.name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_current_acceptance_ledger_is_complete(self) -> None:
        workspaces, automated_complete, backup_complete, human_complete = MODULE.validate_acceptance()
        self.assertEqual(workspaces, 4)
        self.assertEqual(automated_complete, 4)
        self.assertEqual(backup_complete, 4)
        self.assertEqual(human_complete, 0)

    def test_rejects_an_uncovered_in_progress_route(self) -> None:
        def remove_route(value) -> None:
            value["workspace_acceptance"][0]["routes"].pop()

        acceptance = self.temporary_json(MODULE.ACCEPTANCE, remove_route)
        with self.assertRaisesRegex(ValueError, "missing workspace acceptance"):
            MODULE.validate_acceptance(acceptance_path=acceptance)

    def test_rejects_missing_evidence(self) -> None:
        def replace_evidence(value) -> None:
            value["workspace_acceptance"][0]["automated_evidence"][0] = "frontend/e2e/missing.spec.ts"

        acceptance = self.temporary_json(MODULE.ACCEPTANCE, replace_evidence)
        with self.assertRaisesRegex(ValueError, "does not exist"):
            MODULE.validate_acceptance(acceptance_path=acceptance)

    def test_completed_human_review_requires_attribution(self) -> None:
        def complete_without_attribution(value) -> None:
            value["workspace_acceptance"][0]["human_review"]["status"] = "complete"

        acceptance = self.temporary_json(MODULE.ACCEPTANCE, complete_without_attribution)
        with self.assertRaisesRegex(ValueError, "reviewed_by"):
            MODULE.validate_acceptance(acceptance_path=acceptance)


if __name__ == "__main__":
    unittest.main()
