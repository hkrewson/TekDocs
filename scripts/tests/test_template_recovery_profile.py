from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REHEARSAL = ROOT / "tests/rehearsals/rehearse-supported-recovery.sh"


@unittest.skipUnless(shutil.which("docker"), "Compose configuration validation requires the Docker CLI")
class TemplateRecoveryProfileTests(unittest.TestCase):
    def test_verifier_preserves_restored_network_isolation_and_media_custody(self) -> None:
        # Exercise the real Compose helper in configuration-only mode. Running
        # the full rehearsal would create independent source/restore stacks.
        source = REHEARSAL.read_text()
        helper = "compose_for() {" + source.split("compose_for() {", 1)[1].split("\ncleanup() {", 1)[0]
        script = helper + '\nrepository_root=$1\nrestore_environment=$2\ncompose_for "$3" "$4" config --format json\n'
        with tempfile.TemporaryDirectory() as directory:
            for environment, isolated in ((".env.production.example", True), (".env.example", False)):
                with self.subTest(environment=environment):
                    result = subprocess.run(
                        ["sh", "-c", script, "sh", str(ROOT), str(ROOT / ".env.production.example"),
                         str(ROOT / environment), directory],
                        cwd=ROOT, check=True, capture_output=True, text=True,
                    )
                    configuration = json.loads(result.stdout)
                    self.assertEqual(configuration["networks"]["internal"].get("internal", False), isolated)
                    media = [mount for mount in configuration["services"]["migrate"]["volumes"]
                             if mount["target"] == "/app/media"]
                    self.assertEqual(
                        [(mount["type"], mount["source"]) for mount in media], [("volume", "media_data")],
                    )


if __name__ == "__main__":
    unittest.main()
