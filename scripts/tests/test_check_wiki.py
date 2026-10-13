from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("check_wiki", ROOT / "scripts/check-wiki.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WikiCheckoutTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.checkout = Path(directory.name)
        (self.checkout / ".git").mkdir()
        pages = json.loads(MODULE.MANIFEST.read_text())["pages"]
        for page in pages:
            (self.checkout / f"{page['slug']}.md").write_text("# Guide\n")
        (self.checkout / "_Sidebar.md").write_text("[Home](Home)\n")

    def test_complete_required_inventory(self) -> None:
        MODULE.validate(self.checkout)

    def test_existing_supplemental_setup_page_is_a_valid_destination(self) -> None:
        (self.checkout / "Production-Prerequisites.md").write_text("[Setup](TekDocs-Setup)\n")
        (self.checkout / "Home.md").write_text("[Prerequisites](Production-Prerequisites)\n")
        MODULE.validate(self.checkout)

    def test_supplemental_pages_also_require_valid_links(self) -> None:
        (self.checkout / "Production-Prerequisites.md").write_text("[Missing](Missing)\n")
        with self.assertRaisesRegex(ValueError, "unknown local page link"):
            MODULE.validate(self.checkout)

    def test_supplemental_page_does_not_replace_required_page(self) -> None:
        (self.checkout / "Account-security.md").unlink()
        (self.checkout / "Other-security.md").write_text("# Security\n")
        with self.assertRaisesRegex(ValueError, "missing pages"):
            MODULE.validate(self.checkout)

    def test_rejects_unknown_or_traversing_destinations(self) -> None:
        for destination in ("Missing", "../Home", "%2e%2e/Home"):
            with self.subTest(destination=destination):
                (self.checkout / "Home.md").write_text(f"[Bad]({destination})\n")
                with self.assertRaisesRegex(ValueError, "unknown local page link"):
                    MODULE.validate(self.checkout)

    def test_accepts_extension_and_anchor(self) -> None:
        (self.checkout / "Home.md").write_text("[Account](Account-security.md#mfa)\n")
        MODULE.validate(self.checkout)


if __name__ == "__main__":
    unittest.main()
