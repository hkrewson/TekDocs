from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReleaseGatePlanTests(unittest.TestCase):
    def test_standalone_performance_gate_provisions_runtime_before_pytest(self) -> None:
        result = subprocess.run(
            ["make", "-n", "-o", "check-frontend", "test-public-beta-performance"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        commands = result.stdout.splitlines()
        provision = "docker compose run --rm migrate python manage.py provision_runtime_role"
        self.assertIn(provision, commands)
        first_test = next(index for index, command in enumerate(commands) if " pytest " in command)
        self.assertLess(commands.index(provision), first_test)

    def test_release_gate_runs_each_frontend_boundary_once(self) -> None:
        result = subprocess.run(
            ["make", "-n", "release-gate"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        commands = [line.strip() for line in result.stdout.splitlines()]
        self.assertEqual(commands.count("./scripts/frontend-gate.sh test"), 1)
        self.assertEqual(commands.count("./scripts/frontend-gate.sh verify"), 1)
        self.assertEqual(commands.count("./scripts/frontend-gate.sh audit"), 1)

    def test_release_gate_runs_one_sharded_backend_boundary(self) -> None:
        result = subprocess.run(
            ["make", "-n", "release-gate"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        commands = [line.strip() for line in result.stdout.splitlines()]
        pytest_commands = [command for command in commands if " pytest " in command]

        self.assertEqual(
            commands.count("./tests/rehearsals/rehearse-postgres-test-matrix.sh"), 1
        )
        self.assertNotIn("docker compose run --rm migrate pytest --cov", commands)
        performance_prefix = (
            "docker compose run --rm -e TEKDOCS_ENFORCE_LATENCY_BUDGETS=true "
            "migrate pytest "
        )
        self.assertCountEqual(
            pytest_commands,
            [
                performance_prefix
                + "apps/core/tests/test_public_beta_capacity.py -m performance -q -s",
                performance_prefix
                + "apps/core/tests/test_content_performance.py -m performance -q -s",
                performance_prefix
                + "apps/core/tests/test_stabilization_performance.py "
                "apps/core/tests/test_inventory_stabilization.py "
                "apps/core/tests/test_portal_notification_stabilization.py -q -s",
            ],
        )


if __name__ == "__main__":
    unittest.main()
