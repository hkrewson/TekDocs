from __future__ import annotations

import ast
import json
import os
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "rehearsals" / "rehearse-postgres-test-shard.sh"
BUILD_WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


@contextmanager
def plan_environment() -> Iterator[dict[str, str]]:
    with tempfile.TemporaryDirectory() as directory:
        # Planning must never operate a real Compose project in these tests.
        docker = Path(directory) / "docker"
        docker.write_text("#!/bin/sh\nexit 0\n")
        docker.chmod(0o755)
        yield os.environ | {
            "PATH": directory + os.pathsep + os.environ["PATH"],
            "TEKDOCS_POSTGRES_SHARD_LIST_ONLY": "true",
            "DJANGO_SETTINGS_MODULE": "tekdocs.settings.production",
        }


class PostgresShardPlanTests(unittest.TestCase):
    def test_split_core_a_groups_preserve_every_original_module_once(self) -> None:
        with plan_environment() as environment:
            def modules(shard: str) -> list[str]:
                result = subprocess.run([str(RUNNER), shard], cwd=ROOT, check=True,
                                        capture_output=True, text=True, env=environment)
                return [line for line in result.stdout.splitlines() if line.endswith(".py")]

            original = modules("core-a")
            first, second, third = (modules(name) for name in ("core-a-1", "core-a-2", "core-a-3"))
        self.assertTrue(first)
        self.assertTrue(second)
        self.assertTrue(third)
        self.assertEqual(sorted(first + second + third), sorted(original))
        self.assertEqual(len(first + second + third), len(set(first + second + third)))
        self.assertLessEqual(abs(len(second) - len(third)), 1)

    def test_new_discovery_tests_do_not_redistribute_validated_core_modules(self) -> None:
        baseline = json.loads((ROOT / "scripts/tests/fixtures/postgres-core-baseline.json").read_text())
        existing = {name for values in baseline["groups"].values() for name in values}
        with plan_environment() as environment:
            for group, expected in baseline["groups"].items():
                with self.subTest(group=group):
                    actual = []
                    names = ("core-a-2", "core-a-3") if group == "core-a-2" else (group,)
                    for name in names:
                        result = subprocess.run([str(RUNNER), name], cwd=ROOT, check=True,
                                                capture_output=True, text=True, env=environment)
                        actual.extend(line for line in result.stdout.splitlines() if line in existing)
                    self.assertEqual(sorted(actual), sorted(expected))

    def test_slow_core_a_branch_is_split_without_omitting_modules(self) -> None:
        baseline = json.loads((ROOT / "scripts/tests/fixtures/postgres-core-baseline.json").read_text())
        with plan_environment() as environment:
            groups = []
            for name in ("core-a-2", "core-a-3"):
                result = subprocess.run([str(RUNNER), name], cwd=ROOT, check=True,
                                        capture_output=True, text=True, env=environment)
                groups.append([line for line in result.stdout.splitlines() if line.endswith(".py")])
        self.assertEqual(sorted(groups[0] + groups[1]), sorted(baseline["groups"]["core-a-2"]))
        self.assertFalse(set(groups[0]) & set(groups[1]))
        self.assertLessEqual(abs(len(groups[0]) - len(groups[1])), 1)

    def test_combined_coverage_requires_every_split_core_a_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory, plan_environment() as environment:
            coverage = Path(directory)
            for shard in (
                "route-access", "route-methods", "route-session", "accounts",
                "core-a-1", "core-a-2", "core-a-3", "core-b", "core-c",
                "template-migration-a", "template-migration-b", "template-migration-c",
                "migration-foundation", "migration-isolation", "migration-guards",
                "key-entity-migration", "content-key-migration", "diagram-migration",
                "monitored-migration", "client-publication-migration",
            ):
                (coverage / f"coverage.{shard}").write_bytes(b"fixture")

            def combine() -> subprocess.CompletedProcess[str]:
                return subprocess.run([str(ROOT / "scripts/combine-postgres-coverage.sh"), directory],
                                      cwd=ROOT, capture_output=True, text=True, env=environment)

            self.assertEqual(combine().returncode, 0)
            for shard in ("core-a-1", "core-a-2", "core-a-3"):
                with self.subTest(shard=shard):
                    artifact = coverage / f"coverage.{shard}"
                    artifact.unlink()
                    missing = combine()
                    self.assertNotEqual(missing.returncode, 0)
                    self.assertIn(shard, missing.stdout + missing.stderr)
                    artifact.write_bytes(b"fixture")

    def test_partitioned_coverage_requires_the_template_migration_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory, plan_environment() as environment:
            coverage = Path(directory)
            for shard in (
                "route-access", "route-methods", "route-session", "accounts", "core-a", "core-b", "core-c",
                "migration-foundation", "migration-isolation", "migration-guards", "key-entity-migration", "content-key-migration", "diagram-migration", "monitored-migration", "client-publication-migration",
            ):
                (coverage / f"coverage.{shard}").write_bytes(b"fixture")

            def combine() -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [str(ROOT / "scripts/combine-postgres-coverage.sh"), directory],
                    cwd=ROOT, capture_output=True, text=True, env=environment,
                )

            missing = combine()
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("template-migration", missing.stdout + missing.stderr)
            for shard in ("template-migration-a", "template-migration-b", "template-migration-c"):
                (coverage / f"coverage.{shard}").write_bytes(b"fixture")
            self.assertEqual(combine().returncode, 0)
            for shard in ("template-migration-a", "template-migration-b", "template-migration-c", "content-key-migration", "diagram-migration", "monitored-migration", "client-publication-migration"):
                artifact = coverage / f"coverage.{shard}"
                artifact.unlink()
                self.assertNotEqual(combine().returncode, 0)
                artifact.write_bytes(b"fixture")
            for shard in ("template-migration-a", "template-migration-b", "template-migration-c"):
                (coverage / f"coverage.{shard}").unlink()
            (coverage / "coverage.core").write_bytes(b"fixture")
            self.assertEqual(combine().returncode, 0)

    def test_addressed_partition_is_required_for_combined_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory, plan_environment() as environment:
            coverage = Path(directory)
            for shard in (
                "route-access", "route-methods", "route-session", "accounts", "core-a", "core-b", "core-c",
                "template-migration-a", "template-migration-b", "template-migration-c",
                "migration-foundation", "migration-isolation", "migration-guards",
            ):
                (coverage / f"coverage.{shard}").write_bytes(b"fixture")
            result = subprocess.run([str(ROOT / "scripts/combine-postgres-coverage.sh"), directory],
                                    cwd=ROOT, capture_output=True, text=True, env=environment)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("key-entity-migration", result.stdout + result.stderr)

    def test_template_partitions_select_every_function_once(self) -> None:
        source = "apps/core/tests/test_template_enrollment_migration.py"
        tree = ast.parse((ROOT / "backend" / source).read_text())
        expected = {
            f"{source}::{node.name}" for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        }
        selected: list[str] = []
        with plan_environment() as environment:
            for shard in ("template-migration-a", "template-migration-b", "template-migration-c"):
                result = subprocess.run([str(RUNNER), shard], cwd=ROOT, check=True,
                                        capture_output=True, text=True, env=environment)
                nodes = [line for line in result.stdout.splitlines() if "::test_" in line]
                self.assertTrue(nodes)
                selected.extend(nodes)
        self.assertEqual(set(selected), expected)
        self.assertEqual(len(selected), len(expected))

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
            "core-a", "core-a-1", "core-a-2", "core-a-3", "core-b", "core-c", "migration-foundation", "migration-isolation",
            "migration-guards", "runtime", "template-migration",
            "template-migration-a", "template-migration-b", "template-migration-c", "key-entity-migration", "content-key-migration", "diagram-migration", "monitored-migration", "client-publication-migration",
        )
        with plan_environment() as environment:
            for shard in shards:
                with self.subTest(shard=shard):
                    result = subprocess.run(
                        [str(RUNNER), shard], cwd=ROOT, check=True,
                        capture_output=True, text=True, env=environment,
                    )
                    self.assertIn("--ds=tekdocs.settings.test", result.stdout.splitlines())
                    if shard == "template-migration":
                        self.assertEqual(
                            [line for line in result.stdout.splitlines() if line.endswith(".py")],
                            ["apps/core/tests/test_template_enrollment_migration.py"],
                        )

    def test_ci_uses_the_existing_balanced_core_partitions(self) -> None:
        workflow = BUILD_WORKFLOW.read_text()

        self.assertIn(
            "shard: [route-access, route-methods, route-session, accounts, "
            "core-a-1, core-a-2, core-a-3, core-b, core-c, template-migration-a, template-migration-b, template-migration-c, key-entity-migration, content-key-migration, diagram-migration, monitored-migration, client-publication-migration, migration-foundation, migration-isolation, "
            "migration-guards]",
            workflow,
        )
        self.assertIn("timeout-minutes: 30", workflow)

    def test_local_core_partitions_cover_each_core_file_once(self) -> None:
        selected: list[str] = []

        with plan_environment() as environment:
            for shard in ("core-a", "core-b", "core-c", "template-migration", "key-entity-migration", "content-key-migration", "diagram-migration", "monitored-migration", "client-publication-migration"):
                result = subprocess.run(
                    [str(RUNNER), shard], cwd=ROOT, check=True,
                    capture_output=True, text=True, env=environment,
                )
                selected.extend(line for line in result.stdout.splitlines() if line.endswith(".py"))

        expected = sorted(
            str(path.relative_to(ROOT / "backend"))
            for path in (ROOT / "backend" / "apps" / "core" / "tests").glob(
                "test_*.py"
            )
            if path.name != "test_migration_stabilization.py"
        )

        self.assertEqual(sorted(selected), expected)
        self.assertEqual(len(selected), len(set(selected)))

    def test_client_publication_has_a_required_dedicated_partition(self) -> None:
        with plan_environment() as environment:
            result = subprocess.run(
                [str(RUNNER), "client-publication-migration"], cwd=ROOT,
                capture_output=True, text=True, env=environment,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [line for line in result.stdout.splitlines() if line.endswith(".py")],
            ["apps/core/tests/test_client_published_migration.py"],
        )
        self.assertIn("--ds=tekdocs.settings.test", result.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
