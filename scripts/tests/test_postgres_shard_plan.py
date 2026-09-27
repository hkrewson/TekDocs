from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "rehearsals" / "rehearse-postgres-test-shard.sh"


class PostgresShardPlanTests(unittest.TestCase):
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
