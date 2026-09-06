from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "check-ui-language.py"
SPEC = importlib.util.spec_from_file_location("check_ui_language", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the UI language contract module")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UiLanguageContractTests(unittest.TestCase):
    def test_current_catalog_inventory_and_shell_pass(self) -> None:
        entries, reviewed, routes = MODULE.validate_inventory()
        self.assertGreater(entries, 0)
        self.assertGreater(reviewed, 0)
        self.assertGreater(routes, 0)
        self.assertGreater(MODULE.validate_catalog(), 0)
        MODULE.validate_shell_migration()
        MODULE.validate_infrastructure_migration()
        MODULE.validate_supplier_migration()
        MODULE.validate_invoice_migration()
        MODULE.validate_governance_migration()
        MODULE.validate_integration_migration()

    def test_rejects_promotional_or_internal_catalog_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            catalog = Path(temporary_directory) / "catalog.json"
            catalog.write_text(json.dumps({"page.intro": "A powerful canonical experience."}), encoding="utf-8")
            with patch.object(MODULE, "CATALOG", catalog), self.assertRaisesRegex(ValueError, "banned promotional phrase"):
                MODULE.validate_catalog()

            catalog.write_text(json.dumps({"page.intro": "Review the canonical record."}), encoding="utf-8")
            with patch.object(MODULE, "CATALOG", catalog), self.assertRaisesRegex(ValueError, "internal term"):
                MODULE.validate_catalog()

    def test_rejects_missing_route(self) -> None:
        current = json.loads(MODULE.INVENTORY.read_text(encoding="utf-8"))
        current["entries"][0]["routes"].remove("/overview")
        with tempfile.TemporaryDirectory() as temporary_directory:
            inventory = Path(temporary_directory) / "inventory.json"
            inventory.write_text(json.dumps(current), encoding="utf-8")
            with patch.object(MODULE, "INVENTORY", inventory), self.assertRaisesRegex(ValueError, "missing routes: /overview"):
                MODULE.validate_inventory()

    def test_rejects_a_review_without_decisions(self) -> None:
        current = json.loads(MODULE.INVENTORY.read_text(encoding="utf-8"))
        current["entries"][0]["decisions"] = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            inventory = Path(temporary_directory) / "inventory.json"
            inventory.write_text(json.dumps(current), encoding="utf-8")
            with patch.object(MODULE, "INVENTORY", inventory), self.assertRaisesRegex(ValueError, "must record copy decisions"):
                MODULE.validate_inventory()

    def test_rejects_reintroduced_infrastructure_jargon(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "Assets.tsx"
            source.write_text("const label = 'Provenance checksum'\n", encoding="utf-8")
            reviewed_files = {source: {"Provenance checksum"}}
            with patch.object(MODULE, "REVIEWED_INFRASTRUCTURE_FILES", reviewed_files), self.assertRaisesRegex(
                ValueError, "reviewed infrastructure copy returned"
            ):
                MODULE.validate_infrastructure_migration()

    def test_rejects_reintroduced_supplier_jargon(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "Products.tsx"
            source.write_text("const label = 'Reusable validation contracts'\n", encoding="utf-8")
            reviewed_files = {source: {"Reusable validation contracts"}}
            with patch.object(MODULE, "REVIEWED_SUPPLIER_FILES", reviewed_files), self.assertRaisesRegex(
                ValueError, "reviewed supplier copy returned"
            ):
                MODULE.validate_supplier_migration()

    def test_rejects_reintroduced_invoice_jargon_or_browser_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "Invoices.tsx"
            source.write_text("window.confirm('Issue invoice?')\n", encoding="utf-8")
            reviewed_files = {source: {"window.confirm"}}
            with patch.object(MODULE, "REVIEWED_INVOICE_FILES", reviewed_files), self.assertRaisesRegex(
                ValueError, "reviewed invoice copy or confirmation returned"
            ):
                MODULE.validate_invoice_migration()

    def test_rejects_reintroduced_governance_jargon_or_browser_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "Taxonomies.tsx"
            source.write_text("window.confirm('Archive taxonomy?')\n", encoding="utf-8")
            reviewed_files = {source: {"window.confirm"}}
            with patch.object(MODULE, "REVIEWED_GOVERNANCE_FILES", reviewed_files), self.assertRaisesRegex(
                ValueError, "reviewed governance copy or confirmation returned"
            ):
                MODULE.validate_governance_migration()

    def test_rejects_reintroduced_integration_jargon_raw_errors_or_browser_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "Webhooks.tsx"
            source.write_text("window.prompt('Why retry?')\n", encoding="utf-8")
            reviewed_files = {source: {"window.prompt"}}
            with patch.object(MODULE, "REVIEWED_INTEGRATION_FILES", reviewed_files), self.assertRaisesRegex(
                ValueError, "reviewed integration copy, raw error, or browser prompt returned"
            ):
                MODULE.validate_integration_migration()


if __name__ == "__main__":
    unittest.main()
