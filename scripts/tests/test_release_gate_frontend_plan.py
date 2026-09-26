from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReleaseGateFrontendPlanTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
