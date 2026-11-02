"""Publication server lifetime and bounded IPC failure contracts."""

import importlib.util
import json
import secrets
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "publication_protocol", ROOT / "backend/apps/core/tests/publication_acceptance_protocol.py"
)
protocol = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(protocol)


class PublicationAcceptanceProtocolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.marker = Path(self.directory.name) / "browser-finished.json"
        self.budget = ROOT / "frontend/publication-browser-budget.json"
        self.elapsed = 0.0

    def pause(self, seconds):
        self.elapsed += seconds

    def wait(self, pause=None):
        return protocol.wait_for_browser_completion(
            self.marker,
            protocol.completion_timeout_seconds(self.budget),
            clock=lambda: self.elapsed,
            pause=pause or self.pause,
        )

    def test_completion_after_old_server_deadline(self):
        def browser_progress(seconds):
            self.pause(seconds)
            if self.elapsed >= 300:
                self.marker.write_text('{"status":"passed"}')

        self.assertEqual(self.wait(browser_progress), {"status": "passed"})
        self.assertGreaterEqual(self.elapsed, 300)

    def test_early_success_needs_no_wait(self):
        self.marker.write_text('{"status":"passed"}')
        self.assertEqual(self.wait(), {"status": "passed"})
        self.assertEqual(self.elapsed, 0)

    def test_failure_marker_is_preserved(self):
        self.marker.write_text('{"status":"failed"}')
        self.assertEqual(self.wait(), {"status": "failed"})
        self.assertEqual(self.elapsed, 0)

    def test_missing_marker_expires_with_finite_failure(self):
        with self.assertRaisesRegex(AssertionError, "browser did not complete"):
            self.wait()
        self.assertAlmostEqual(self.elapsed, 960, delta=0.11)

    def test_shared_budget_preserves_case_limit_and_bounds_suite(self):
        budget = json.loads(self.budget.read_text())
        self.assertEqual(budget["test_timeout_ms"], 120000)
        self.assertGreater(budget["suite_timeout_ms"], 7 * budget["test_timeout_ms"])
        self.assertEqual(protocol.completion_timeout_seconds(self.budget), 960)

    def test_invalid_or_unbounded_budget_is_rejected(self):
        path = Path(self.directory.name) / "budget.json"
        for value in ([], {}, {
            "test_timeout_ms": True, "suite_timeout_ms": 900000, "controller_grace_ms": 60000,
        }, {
            "test_timeout_ms": 120000, "suite_timeout_ms": 900000, "controller_grace_ms": 60001,
        }, {
            "test_timeout_ms": 120000, "suite_timeout_ms": 1800000, "controller_grace_ms": 60000,
        }):
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "Invalid publication browser budget"):
                    protocol.completion_timeout_seconds(path)

    def test_server_failure_locations_survive_without_private_exception_values(self):
        value = secrets.token_hex(24)
        path = ROOT / "backend/apps/core/tests/cross_workspace_fixture.py"
        try:
            exec(compile("raise AssertionError(value)", str(path), "exec"), {"value": value})
        except AssertionError as error:
            report = protocol.safe_failure_report(error, "call")
        checked = protocol.validate_failure_report(report)
        self.assertEqual(checked["category"], "assertion")
        self.assertIn({"file": "apps/core/tests/cross_workspace_fixture.py", "line": 1}, checked["locations"])
        self.assertNotIn(value, json.dumps(checked))
        self.assertNotIn("message", checked)

    def test_server_failure_report_rejects_values_unknown_fields_and_escaping_paths(self):
        report = {"version": 1, "phase": "call", "category": "assertion", "locations": []}
        for candidate in (
            {**report, "message": secrets.token_hex(24)},
            {**report, "phase": "private-value"},
            {**report, "locations": [{"file": "../.env", "line": 1}]},
            {**report, "locations": [{"file": "apps/core/tests/cross_workspace_fixture.py", "line": True}]},
        ):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                protocol.validate_failure_report(candidate)
