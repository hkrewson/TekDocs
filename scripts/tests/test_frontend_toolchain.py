from pathlib import Path
import json
import shutil
import tempfile
import unittest

from scripts.check_frontend_toolchain import ROOT, REHEARSALS, validate


class FrontendToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("frontend/package.json", "frontend/package-lock.json", "frontend/Dockerfile.e2e",
                     *("tests/rehearsals/" + name for name in REHEARSALS)):
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)

    def test_current_versions_pass(self):
        validate(self.root)

    def test_mismatched_coverage_is_rejected(self):
        for name in ("package.json", "package-lock.json"):
            path = self.root / "frontend" / name
            data = json.loads(path.read_text())
            if name == "package.json":
                data["devDependencies"]["@vitest/coverage-v8"] = "4.1.10"
            else:
                data["packages"][""]["devDependencies"]["@vitest/coverage-v8"] = "4.1.10"
                data["packages"]["node_modules/@vitest/coverage-v8"]["version"] = "4.1.10"
            path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "updated together"):
            validate(self.root)

    def test_old_browser_image_is_rejected(self):
        path = self.root / "frontend/Dockerfile.e2e"
        path.write_text(path.read_text().replace("ARG PLAYWRIGHT_VERSION=", "ARG OLD_VERSION="))
        with self.assertRaisesRegex(ValueError, "image version"):
            validate(self.root)

    def test_each_stale_rehearsal_is_rejected(self):
        for name in REHEARSALS:
            path = self.root / "tests/rehearsals" / name
            original = path.read_text()
            path.write_text(original.replace("playwright_version=", "old_version="))
            with self.assertRaisesRegex(ValueError, "matching Playwright"):
                validate(self.root)
            path.write_text(original)
