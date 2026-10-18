from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "scan_source_secrets", Path(__file__).resolve().parents[1] / "scan_source_secrets.py"
)
assert SPEC and SPEC.loader
scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan)


class SourceScanTests(unittest.TestCase):
    def test_includes_working_changes_and_new_source_but_excludes_private_ignored_data(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as output:
            repo = Path(root)
            subprocess.run(["git", "init", "-q", root], check=True)
            (repo / ".gitignore").write_text("artifacts/\n.env\nbuild/\n")
            (repo / "tracked.py").write_text("original source")
            (repo / "removed.py").write_text("removed source")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            (repo / "tracked.py").write_text("updated working source")
            (repo / "removed.py").unlink()
            (repo / "new.py").write_text("new source")
            (repo / "artifacts").mkdir()
            (repo / "artifacts" / "access.txt").write_text("private synthetic fixture")
            (repo / ".env").write_text("private configuration")
            (repo / "build").mkdir()
            (repo / "build" / "stale.py").write_text("generated copy")
            destination = Path(output)
            self.assertEqual(scan.export_sources(repo, destination), 3)
            self.assertEqual((destination / "tracked.py").read_text(), "updated working source")
            self.assertEqual((destination / "new.py").read_text(), "new source")
            self.assertEqual(sorted(p.name for p in destination.iterdir()), [".gitignore", "new.py", "tracked.py"])

    def test_refuses_symlinks_to_private_files(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as output:
            subprocess.run(["git", "init", "-q", root], check=True)
            private = Path(output) / "private.txt"
            private.write_text("private fixture")
            (Path(root) / "linked.py").symlink_to(private)
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                scan.export_sources(Path(root), Path(output) / "export")


if __name__ == "__main__":
    unittest.main()
