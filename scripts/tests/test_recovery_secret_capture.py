from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RecoverySecretCaptureTests(unittest.TestCase):
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
