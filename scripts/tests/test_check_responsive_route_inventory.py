from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "check-responsive-route-inventory.py"
SPEC = importlib.util.spec_from_file_location("check_responsive_route_inventory", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the responsive route inventory module")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ResponsiveRouteInventoryTests(unittest.TestCase):
    def temporary_inventory(self, transform) -> Path:
        entries = json.loads(MODULE.INVENTORY.read_text(encoding="utf-8"))
        transform(entries)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "routes.json"
        path.write_text(json.dumps(entries), encoding="utf-8")
        return path

    def test_current_router_and_inventory_agree(self) -> None:
        routes, complete, in_progress = MODULE.validate_inventory()
        self.assertGreater(routes, 0)
        self.assertGreater(complete, 0)
        self.assertGreater(in_progress, 0)

    def test_rejects_a_route_missing_from_the_inventory(self) -> None:
        path = self.temporary_inventory(lambda entries: entries.pop())
        with self.assertRaisesRegex(ValueError, "missing routes"):
            MODULE.validate_inventory(inventory_path=path)

    def test_rejects_a_stale_inventory_route(self) -> None:
        def add_stale(entries) -> None:
            entries.append({
                "route": "/retired",
                "source": "frontend/src/App.tsx",
                "status": "pending",
                "evidence": [],
                "states": MODULE.DEFAULT_STATES,
            })

        path = self.temporary_inventory(add_stale)
        with self.assertRaisesRegex(ValueError, "stale routes"):
            MODULE.validate_inventory(inventory_path=path)

    def test_requires_evidence_and_specific_states_for_started_routes(self) -> None:
        def remove_evidence(entries) -> None:
            entry = next(item for item in entries if item["status"] == "complete")
            entry["evidence"] = []

        path = self.temporary_inventory(remove_evidence)
        with self.assertRaisesRegex(ValueError, "must record evidence"):
            MODULE.validate_inventory(inventory_path=path)

        def restore_default_states(entries) -> None:
            entry = next(item for item in entries if item["status"] == "complete")
            entry["states"] = MODULE.DEFAULT_STATES

        path = self.temporary_inventory(restore_default_states)
        with self.assertRaisesRegex(ValueError, "must replace the default state inventory"):
            MODULE.validate_inventory(inventory_path=path)


if __name__ == "__main__":
    unittest.main()
