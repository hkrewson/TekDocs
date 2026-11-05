from __future__ import annotations

import re
import unittest
from pathlib import Path

from scripts.ci_lane import classify


ROOT = Path(__file__).resolve().parents[2]


class CILanePolicyTests(unittest.TestCase):
    def test_documentation_only_changes_use_the_policy_lane(self) -> None:
        decision = classify(
            "pull_request",
            ["README.md", "docs/PRODUCT_BOUNDARY.md", "planning/releases/README.md"],
        )

        self.assertEqual(decision.lane, "documentation")
        self.assertFalse(decision.code)
        self.assertFalse(decision.integration)

    def test_pull_request_code_uses_fast_validation(self) -> None:
        decision = classify("pull_request", ["backend/apps/core/models.py"])

        self.assertEqual(decision.lane, "pull-request")
        self.assertTrue(decision.code)
        self.assertFalse(decision.integration)

    def test_main_code_uses_full_integration(self) -> None:
        decision = classify("push", ["frontend/src/App.tsx"])

        self.assertEqual(decision.lane, "integration")
        self.assertTrue(decision.code)
        self.assertTrue(decision.integration)

    def test_manual_runs_fail_closed_to_full_integration(self) -> None:
        decision = classify("workflow_dispatch", [])

        self.assertEqual(decision.lane, "integration")
        self.assertTrue(decision.code)
        self.assertTrue(decision.integration)

    def test_missing_change_inventory_fails_closed(self) -> None:
        decision = classify("push", [])

        self.assertTrue(decision.code)
        self.assertTrue(decision.integration)

    def test_workflows_and_branch_contract_define_one_authority_per_state(self) -> None:
        build = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        codeql = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
        policy = (ROOT / "planning/ci-and-environment-state.md").read_text(encoding="utf-8")

        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", build)
        self.assertIn("code: ${{ steps.lane.outputs.code }}", build)
        self.assertIn("integration: ${{ steps.lane.outputs.integration }}", build)
        self.assertIn("needs.prepare.outputs.integration == 'true'", build)
        self.assertIn("name: Validation passed", build)
        self.assertIn("python3 scripts/ci_validation_gate.py", build)
        self.assertIn("if: ${{ always() }}", build)
        self.assertNotIn("  pull_request:\n", codeql.split("permissions:", 1)[0])
        self.assertIn('cron: "17 7 * * 3"', codeql)
        self.assertIn("`main` is the development and integration authority", policy)
        self.assertIn("Production has no mutable Git branch", policy)
        self.assertIn("`receipts/vX.Y.Z`", policy)

    def test_expensive_build_jobs_require_the_integration_lane(self) -> None:
        build = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")

        def job(name: str) -> str:
            match = re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)", build)
            self.assertIsNotNone(match)
            return match.group(1) if match is not None else ""

        for name in ("backend", "frontend", "security"):
            with self.subTest(name=name):
                self.assertIn("if: needs.prepare.outputs.code == 'true'", job(name))
        for name in (
            "runtime-authorization",
            "postgres-shards",
            "postgres-coverage",
            "browser",
            "live-workspace",
            "diagram-exports",
            "production-containers",
        ):
            with self.subTest(name=name):
                self.assertIn("if: needs.prepare.outputs.integration == 'true'", job(name))

        gate = job("validation-gate")
        for name in (
            "prepare",
            "backend",
            "frontend",
            "security",
            "runtime-authorization",
            "postgres-shards",
            "postgres-coverage",
            "browser",
            "live-workspace",
            "diagram-exports",
            "production-containers",
            "release-codeql",
            "release-extended",
            "publish-containers",
        ):
            with self.subTest(gate_need=name):
                self.assertIn(f"- {name}", gate)


if __name__ == "__main__":
    unittest.main()
