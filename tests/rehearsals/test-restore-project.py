"""Read-only Compose checks for the actual restore wrapper; no containers run."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RestoreProjectTests(unittest.TestCase):
    def test_media_preflight_precedes_destructive_operations(self):
        source = (ROOT / "scripts/tekdocs-restore.sh").read_text()
        authenticate = source.index("crypto decrypt --label media")
        preflight = source.index("-m tekdocs.recovery_preflight --kind media /recovery/media.tar")
        destroy = source.index("restore_compose down --volumes")
        self.assertLess(authenticate, preflight)
        self.assertLess(preflight, destroy)

    def test_secret_preflight_precedes_extraction_and_destructive_operations(self):
        source = (ROOT / "scripts/tekdocs-restore.sh").read_text()
        authenticate = source.index("crypto decrypt --label deployment-secrets")
        preflight = source.index("-m tekdocs.recovery_preflight /recovery/deployment-secrets.tar")
        extract = source.index('tar -xf "$work_directory/deployment-secrets.tar"')
        destroy = source.index("restore_compose down --volumes")
        self.assertLess(authenticate, preflight)
        self.assertLess(preflight, extract)
        self.assertLess(extract, destroy)

    def test_confirmed_project_wins_over_inherited_environment(self):
        source = (ROOT / "scripts/tekdocs-restore.sh").read_text()
        wrapper = "restore_compose() {" + source.split("restore_compose() {", 1)[1].split("\n}", 1)[0] + "\n}"
        with tempfile.TemporaryDirectory(prefix="tekdocs-restore-project-") as directory:
            root = Path(directory)
            for filename in (
                "compose.yml", "compose.production.yml", "compose.secret-files.yml",
                "compose.bootstrap-secret.yml", "compose.recovery-isolated.yml",
            ):
                (root / filename).write_text(
                    "services:\n  fixture:\n    image: scratch\n"
                    "    volumes:\n      - data:/fixture\n"
                    "volumes:\n  data:\n    name: ${COMPOSE_PROJECT_NAME}_fixture\n"
                )
            environment_file = root / "fixture.env"
            environment_file.write_text("COMPOSE_PROJECT_NAME=confirmed-fixture\n")
            for isolated in ("false", "true"):
                for inherited in (None, "unconfirmed-fixture"):
                    with self.subTest(isolated=isolated, inherited=inherited):
                        environment = os.environ.copy()
                        for name in tuple(environment):
                            if name.startswith("COMPOSE_"):
                                del environment[name]
                        environment.update(
                            repository_root=str(root), environment_file=str(environment_file),
                            project_name="confirmed-fixture", network_isolated=isolated,
                        )
                        if inherited:
                            environment["COMPOSE_PROJECT_NAME"] = inherited
                        # Execute only the checked-in wrapper and a fixed read-only command.
                        result = subprocess.run(  # noqa: S603
                            ["/bin/sh", "-c", wrapper + "\nrestore_compose config --format json"],
                            env=environment, capture_output=True, text=True, check=True,
                        )
                        config = json.loads(result.stdout)
                        self.assertEqual(config["name"], "confirmed-fixture")
                        self.assertEqual(config["volumes"]["data"]["name"], "confirmed-fixture_fixture")


if __name__ == "__main__":
    unittest.main()
