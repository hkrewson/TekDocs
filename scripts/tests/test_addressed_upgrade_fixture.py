from __future__ import annotations

import ast
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "35e93cabdfa3e1ae2b32f447ca7a09f21f6d16a8"


class AddressedUpgradeFixtureTests(unittest.TestCase):
    def test_seed_top_level_imports_exist_on_supported_baseline(self):
        fixtures = [ROOT / "backend/apps/core/tests" / name for name in ("key_entity_fixture.py", "content_key_fixture.py", "diagram_fixture.py")]
        tree = ast.Module(body=[node for fixture in fixtures for node in ast.parse(fixture.read_text()).body], type_ignores=[])
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith("apps.core."):
                continue
            path = "backend/" + node.module.replace(".", "/") + ".py"
            old = subprocess.run(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT,
                                 capture_output=True, text=True, check=True)
            exports = set()
            for item in ast.parse(old.stdout).body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    exports.add(item.name)
                elif isinstance(item, (ast.Import, ast.ImportFrom)):
                    exports.update(alias.asname or alias.name for alias in item.names)
            for name in node.names:
                with self.subTest(module=node.module, name=name.name):
                    self.assertIn(name.name, exports)


if __name__ == "__main__":
    unittest.main()
