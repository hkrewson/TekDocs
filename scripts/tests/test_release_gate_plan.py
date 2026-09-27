from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReleaseGatePlanTests(unittest.TestCase):
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

    def test_release_gate_runs_backend_coverage_once(self) -> None:
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
            commands.count("docker compose run --rm migrate pytest --cov"), 1
        )
        self.assertEqual(len(pytest_commands), 3)
        self.assertTrue(
            any("test_public_beta_capacity.py" in command for command in pytest_commands)
        )
        self.assertTrue(
            any(
                "TEKDOCS_ENFORCE_LATENCY_BUDGETS=true" in command
                for command in pytest_commands
            )
        )


if __name__ == "__main__":
    unittest.main()
