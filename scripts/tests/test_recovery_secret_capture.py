from __future__ import annotations

import io
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RecoverySecretCaptureTests(unittest.TestCase):
    def test_recovery_rehearsal_keys_are_readable_through_service_mounts(self) -> None:
        for filename in ("rehearse-supported-recovery.sh", "rehearse-repository-foundation.sh"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = (ROOT / "tests/rehearsals" / filename).read_text()
                function = "copy_secret() {" + source.split("copy_secret() {", 1)[1].split("\n}", 1)[0] + "\n}"
                environment = root / "fixture.env"
                environment.write_text("FIXTURE_VALUE=synthetic-test-value\n")
                keys = root / "keys"
                keys.mkdir(mode=0o700)
                subprocess.run(
                    ["sh", "-c", function + "\ncopy_secret FIXTURE_VALUE fixture"],
                    env={**os.environ, "source_environment": str(environment), "source_secrets": str(keys)},
                    capture_output=True, check=True,
                )
                self.assertEqual(stat.S_IMODE(keys.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((keys / "fixture").stat().st_mode), 0o444)

    def test_plaintext_check_handles_option_like_values_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tekdocs-plaintext-test-") as directory:
            artifact = Path(directory) / "artifact"
            artifact.write_text("-d-synthetic-fixture\n")
            for pattern, filename, status in (
                ("-d-synthetic-fixture", artifact, 1),
                ("-d-absent-fixture", artifact, 0),
                ("-d-synthetic-fixture", Path(directory) / "missing", 2),
            ):
                with self.subTest(pattern=pattern, filename=filename):
                    result = subprocess.run(
                        ["sh", "-c", '. "$1"; recovery_assert_no_plaintext "$2" "$3"',
                         "sh", str(ROOT / "scripts/lib/recovery-secret-capture.sh"), pattern, str(filename)],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, status)
                    self.assertNotIn(pattern, result.stdout + result.stderr)

    def test_capture_contains_only_selected_keys_even_with_host_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tekdocs-secret-capture-test-") as directory:
            source = Path(directory)
            key = source / "django_secret_key"
            key.write_bytes(b"synthetic-fixture-not-a-credential\n")
            (source / "unselected.txt").write_bytes(b"must not be archived")
            if sys.platform == "darwin":
                subprocess.run(["xattr", "-w", "com.apple.test", "synthetic", str(key)], check=True)
            result = subprocess.run(
                ["sh", "-c", '. "$1"; recovery_secret_tar "$2" django_secret_key',
                 "sh", str(ROOT / "scripts/lib/recovery-secret-capture.sh"), directory],
                check=True, capture_output=True,
            )
            with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
                self.assertEqual(archive.getnames(), ["django_secret_key"])
                self.assertTrue(archive.getmember("django_secret_key").isfile())
                self.assertEqual(archive.extractfile("django_secret_key").read(), key.read_bytes())


if __name__ == "__main__":
    unittest.main()
