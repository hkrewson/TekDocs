from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "check_renderer_dependency_contract.py"
SPEC = importlib.util.spec_from_file_location("check_renderer_dependency_contract", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the renderer dependency contract checker")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RendererDependencyContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        for directory in ("frontend", "renderer", ".github"):
            (self.root / directory).mkdir(parents=True)
        self.write_json(
            "frontend/package.json",
            {
                "dependencies": {"mermaid": "11.16.1"},
                "overrides": {
                    "@typescript-eslint/typescript-estree": {"minimatch": "11.0.4"},
                    "katex": "0.18.3",
                },
            },
        )
        self.write_json(
            "frontend/package-lock.json",
            {
                "packages": {
                    "": {"dependencies": {"mermaid": "11.16.1"}},
                    "node_modules/@typescript-eslint/typescript-estree/node_modules/minimatch": {
                        "version": "11.0.4"
                    },
                    "node_modules/katex": {"version": "0.18.3"},
                    "node_modules/mermaid": {"version": "11.16.1"},
                    "node_modules/zod": {"version": "4.6.7"},
                }
            },
        )
        self.write_json(
            "renderer/package.json",
            {
                "dependencies": {"@mermaid-js/mermaid-cli": "11.16.0", "puppeteer": "25.7.0"},
                "overrides": {"katex": "0.18.3"},
            },
        )
        self.write_json(
            "renderer/package-lock.json",
            {
                "packages": {
                    "": {
                        "dependencies": {
                            "@mermaid-js/mermaid-cli": "11.16.0",
                            "puppeteer": "25.7.0",
                        }
                    },
                    "node_modules/@mermaid-js/mermaid-cli": {"version": "11.16.0"},
                    "node_modules/katex": {"version": "0.18.3"},
                    "node_modules/mermaid": {"version": "11.16.1"},
                    "node_modules/puppeteer": {"version": "25.7.0"},
                    "node_modules/zod": {"version": "4.6.7"},
                }
            },
        )
        self.write(
            "renderer/Dockerfile",
            "\n".join(
                (
                    "FROM node:24-alpine@sha256:" + "a" * 64,
                    "ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser",
                    "ARG CHROMIUM_SERIES=152",
                    'RUN case "$installed" in "Chromium ${CHROMIUM_SERIES}."*) : ;; esac',
                    "    && printf '%s\\n' \"$installed\" > /chromium-version",
                )
            ),
        )
        self.write("renderer/mermaid-config.json", "{}\n")
        self.write("renderer/puppeteer-config.json", "{}\n")
        self.write("renderer/worker.mjs", "export {}\n")
        self.write(
            ".github/dependabot.yml",
            """updates:
  - package-ecosystem: npm
    directory: /frontend
  - package-ecosystem: npm
    directory: /renderer
  - package-ecosystem: docker
    directory: /renderer
""",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, relative: str, content: str) -> None:
        (self.root / relative).write_text(content, encoding="utf-8")

    def write_json(self, relative: str, content: dict[str, object]) -> None:
        self.write(relative, json.dumps(content))

    def read_json(self, relative: str) -> dict[str, object]:
        return json.loads((self.root / relative).read_text(encoding="utf-8"))

    def test_records_aligned_exact_versions_and_checksums(self) -> None:
        contract = MODULE.build_contract(self.root)
        self.assertEqual(contract["schema_version"], "tekdocs-renderer-dependency-contract/v1")
        self.assertEqual(contract["versions"]["frontend_mermaid"], "11.16.1")
        self.assertEqual(contract["versions"]["renderer_mermaid"], "11.16.1")
        self.assertEqual(contract["versions"]["katex"], "0.18.3")
        self.assertEqual(contract["versions"]["typescript_estree_minimatch"], "11.0.4")
        self.assertEqual(contract["versions"]["zod"], ["4.6.7"])
        self.assertEqual(contract["versions"]["chromium_series"], 152)
        self.assertEqual(set(contract["contract_file_sha256"]), set(MODULE.CONTRACT_FILES))

    def test_rejects_version_ranges(self) -> None:
        package = self.read_json("renderer/package.json")
        package["dependencies"]["puppeteer"] = "^25.7.0"
        self.write_json("renderer/package.json", package)
        with self.assertRaisesRegex(MODULE.ContractError, "exact semantic version"):
            MODULE.build_contract(self.root)

    def test_rejects_manifest_and_lock_drift(self) -> None:
        lock = self.read_json("renderer/package-lock.json")
        lock["packages"]["node_modules/@mermaid-js/mermaid-cli"]["version"] = "11.15.0"
        self.write_json("renderer/package-lock.json", lock)
        with self.assertRaisesRegex(MODULE.ContractError, "Mermaid CLI versions must match"):
            MODULE.build_contract(self.root)

    def test_rejects_preview_and_export_mermaid_drift(self) -> None:
        lock = self.read_json("renderer/package-lock.json")
        lock["packages"]["node_modules/mermaid"]["version"] = "11.15.0"
        self.write_json("renderer/package-lock.json", lock)
        with self.assertRaisesRegex(MODULE.ContractError, "Preview and export Mermaid versions must match"):
            MODULE.build_contract(self.root)

    def test_rejects_vulnerable_katex_resolution(self) -> None:
        lock = self.read_json("frontend/package-lock.json")
        lock["packages"]["node_modules/katex"]["version"] = "0.16.47"
        self.write_json("frontend/package-lock.json", lock)
        with self.assertRaisesRegex(MODULE.ContractError, "KaTeX"):
            MODULE.build_contract(self.root)

    def test_rejects_vulnerable_typescript_estree_minimatch(self) -> None:
        lock = self.read_json("frontend/package-lock.json")
        lock["packages"]["node_modules/@typescript-eslint/typescript-estree/node_modules/minimatch"][
            "version"
        ] = "10.2.6"
        self.write_json("frontend/package-lock.json", lock)
        with self.assertRaisesRegex(MODULE.ContractError, "minimatch"):
            MODULE.build_contract(self.root)

    def test_rejects_vulnerable_zod_resolution(self) -> None:
        lock = self.read_json("frontend/package-lock.json")
        lock["packages"]["node_modules/zod"]["version"] = "4.4.3"
        self.write_json("frontend/package-lock.json", lock)
        with self.assertRaisesRegex(MODULE.ContractError, "Zod"):
            MODULE.build_contract(self.root)

    def test_rejects_prereleases_at_security_floor(self) -> None:
        for value, minimum in (
            ("0.18.2-rc.1", MODULE.PATCHED_KATEX),
            ("11.0.1-beta.1", MODULE.PATCHED_MINIMATCH),
            ("4.6.6-rc.1", MODULE.PATCHED_ZOD),
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(MODULE.ContractError, "stable release"):
                    MODULE.patched_version(value, "security dependency", minimum)

    def test_rejects_missing_chromium_build_assertion(self) -> None:
        dockerfile = (self.root / "renderer/Dockerfile").read_text(encoding="utf-8")
        self.write("renderer/Dockerfile", dockerfile.replace("> /chromium-version", "> /tmp/version"))
        with self.assertRaisesRegex(MODULE.ContractError, "Chromium runtime assertion"):
            MODULE.build_contract(self.root)

    def test_contract_is_deterministic_and_binds_configuration(self) -> None:
        first = MODULE.build_contract(self.root)
        second = MODULE.build_contract(self.root)
        self.assertEqual(first, second)
        self.write("renderer/mermaid-config.json", '{"theme":"base"}\n')
        changed = MODULE.build_contract(self.root)
        self.assertNotEqual(
            first["contract_file_sha256"]["renderer/mermaid-config.json"],
            changed["contract_file_sha256"]["renderer/mermaid-config.json"],
        )


if __name__ == "__main__":
    unittest.main()
