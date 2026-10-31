from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "rehearsals" / "rehearse-postgres-test-shard.sh"
BUILD_WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


class PostgresShardPlanTests(unittest.TestCase):
    def test_diagram_unit_gate_overrides_inherited_production_settings(self) -> None:
        result = subprocess.run(
            ["make", "--dry-run", "test-diagram-exports"], cwd=ROOT,
            check=True, capture_output=True, text=True,
        )
        invocations = [line for line in result.stdout.splitlines() if " pytest " in line]
        self.assertTrue(invocations)
        for invocation in invocations:
            self.assertIn("--ds=tekdocs.settings.test", invocation)

    def test_all_shard_plans_override_inherited_production_settings(self) -> None:
        shards = (
            "route-access", "route-methods", "route-session", "accounts", "core",
            "core-a", "core-b", "core-c", "migration-foundation", "migration-isolation",
            "migration-guards", "runtime",
        )
        with tempfile.TemporaryDirectory() as directory:
            # Planning must never operate a real Compose project in this test.
            docker = Path(directory) / "docker"
            docker.write_text("#!/bin/sh\nexit 0\n")
            docker.chmod(0o755)
            environment = os.environ | {
                "PATH": directory + os.pathsep + os.environ["PATH"],
                "TEKDOCS_POSTGRES_SHARD_LIST_ONLY": "true",
                "DJANGO_SETTINGS_MODULE": "tekdocs.settings.production",
            }
            for shard in shards:
                with self.subTest(shard=shard):
                    result = subprocess.run(
                        [str(RUNNER), shard], cwd=ROOT, check=True,
                        capture_output=True, text=True, env=environment,
                    )
                    self.assertIn("--ds=tekdocs.settings.test", result.stdout.splitlines())

    def test_ci_uses_the_existing_balanced_core_partitions(self) -> None:
        workflow = BUILD_WORKFLOW.read_text()

        self.assertIn(
            "shard: [route-access, route-methods, route-session, accounts, "
            "core-a, core-b, core-c, migration-foundation, migration-isolation, "
            "migration-guards]",
            workflow,
        )

    def test_local_core_partitions_cover_each_core_file_once(self) -> None:
        environment = os.environ | {"TEKDOCS_POSTGRES_SHARD_LIST_ONLY": "true"}
        selected: list[str] = []

        for shard in ("core-a", "core-b", "core-c"):
            result = subprocess.run(
                [str(RUNNER), shard],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            selected.extend(
                line
                for line in result.stdout.splitlines()
                if line.endswith(".py")
            )

        expected = sorted(
            str(path.relative_to(ROOT / "backend"))
            for path in (ROOT / "backend" / "apps" / "core" / "tests").glob(
                "test_*.py"
            )
            if path.name != "test_migration_stabilization.py"
        )

        self.assertEqual(sorted(selected), expected)
        self.assertEqual(len(selected), len(set(selected)))


if __name__ == "__main__":
    unittest.main()
