import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "live_workspace_diagnostics.py"


class LiveWorkspaceDiagnosticsTests(unittest.TestCase):
    def invoke(self, *args, source=""):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], input=source,
            text=True, capture_output=True, check=False,
        )

    def test_worker_and_scheduler_signals_exclude_values_and_identifiers(self):
        report = self.invoke("logs", source="\n".join([
            "worker-1 | Task apps.core.tasks.dispatch_outbox_events[private-id] received",
            "worker-1 | Task apps.core.tasks.dispatch_outbox_events[private-id] succeeded in 0.2s: 3",
            "worker-1 | Task apps.core.tasks.dispatch_outbox_events[private-id] raised unexpected: private-value",
            "scheduler-1 | Sending due task dispatch-transactional-outbox (apps.core.tasks.dispatch_outbox_events)",
            "worker-1 | ERROR secret@example.invalid credential-value",
            "unrelated private-value credential-value private-id",
        ]))
        self.assertEqual(report.returncode, 0)
        self.assertEqual(json.loads(report.stdout), {
            "schema_version": 1, "input_truncated": False,
            "outbox_received": 1, "outbox_succeeded": 1, "outbox_failed": 1,
            "outbox_scheduled": 1, "worker_errors": 1, "scheduler_errors": 0,
        })
        for value in ("private-id", "private-value", "credential-value", "secret@example.invalid"):
            self.assertNotIn(value, report.stdout + report.stderr)

    def test_log_input_is_bounded(self):
        for source in ("private-value\n" * 100_000, "é" * 32_769):
            with self.subTest(multibyte=source.startswith("é")):
                report = self.invoke("logs", source=source)
                self.assertEqual(report.returncode, 0)
                self.assertTrue(json.loads(report.stdout)["input_truncated"])
                self.assertLess(len(report.stdout), 512)
                self.assertNotIn("private-value", report.stdout + report.stderr)

    def test_service_state_preserves_oom_signal_without_extra_fields(self):
        report = self.invoke("service", "worker", source=json.dumps({
            "running": False, "restarting": False, "oom_killed": True, "exit_code": 137,
            "private-value": "credential-value",
        }))
        self.assertEqual(report.returncode, 0)
        self.assertEqual(json.loads(report.stdout), {
            "schema_version": 1, "service": "worker", "running": False,
            "restarting": False, "oom_killed": True, "exit_code": 137,
        })

    def test_invalid_service_data_is_value_free(self):
        for source in ('', 'private-value', '{"running":"private-value"}', '[]'):
            with self.subTest(source=source):
                report = self.invoke("service", "worker", source=source)
                self.assertNotEqual(report.returncode, 0)
                self.assertEqual(json.loads(report.stdout), {
                    "schema_version": 1, "service": "worker", "state": "unavailable",
                })
                self.assertNotIn("private-value", report.stdout + report.stderr)

    def test_invalid_arguments_are_not_echoed(self):
        report = self.invoke("service", "private-value")
        self.assertNotEqual(report.returncode, 0)
        self.assertNotIn("private-value", report.stdout + report.stderr)

    def test_rehearsal_preserves_failure_and_diagnostics_before_cleanup(self):
        root = SCRIPT.parent.parent
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            for folder in ("scripts", "tests/rehearsals", "frontend", "bin"):
                (fixture / folder).mkdir(parents=True)
            for name in ("scripts/live_workspace_diagnostics.py", "scripts/live_workspace_diagnostics.sql", "tests/rehearsals/rehearse-live-workspace-e2e.sh", "frontend/package-lock.json"):
                shutil.copy2(root / name, fixture / name)
            bootstrap = fixture / "scripts/bootstrap-env.sh"
            bootstrap.write_text('#!/bin/sh\n: > "$1"\n')
            bootstrap.chmod(0o755)
            docker = fixture / "bin/docker"
            docker.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if Path(os.environ['FIXTURE_CLEANUP']).exists():
    sys.exit(1)
if args[0] == 'inspect' or 'ps' in args or 'exec' in args:
    print('private-container-id private-path private-error', file=sys.stderr)
if args[0] == 'inspect':
    if os.environ.get('FIXTURE_SERVICE_UNAVAILABLE'):
        sys.exit(23)
    print(json.dumps({'running':False,'restarting':False,'oom_killed':True,'exit_code':137,'extra':'private-value'}))
elif 'build' in args:
    sys.exit(37)
elif 'ps' in args and args[-1] == 'worker':
    print('fixture-worker')
elif 'logs' in args and 'scheduler' in args:
    print('worker-1 | Task apps.core.tasks.dispatch_outbox_events[private-id] raised unexpected: private-value')
elif 'exec' in args:
    if 'db' not in args or os.environ.get('FIXTURE_DB_UNAVAILABLE'):
        sys.exit(23)  # The migration service has exited, like hosted CI.
    print(json.dumps({'schema_version':1,'outbox':{'pending':3},'inbox':{'client_portal':0}}))
elif 'down' in args:
    Path(os.environ['FIXTURE_CLEANUP']).touch()
''')
            docker.chmod(0o755)
            cleanup = fixture / "cleaned"
            report = subprocess.run(
                ["sh", str(fixture / "tests/rehearsals/rehearse-live-workspace-e2e.sh")],
                capture_output=True, text=True, check=False,
                env={**os.environ, "PATH": str(fixture / "bin") + os.pathsep + os.environ["PATH"], "FIXTURE_CLEANUP": str(cleanup)},
            )
            self.assertEqual(report.returncode, 37)
            self.assertTrue(cleanup.exists())
            packets = [json.loads(line) for line in report.stderr.splitlines() if line.startswith('{')]
            worker = next(packet for packet in packets if packet.get("service") == "worker")
            self.assertTrue(worker["oom_killed"])
            self.assertEqual(worker["exit_code"], 137)
            self.assertEqual(next(packet for packet in packets if "outbox_failed" in packet)["outbox_failed"], 1)
            self.assertEqual(next(packet for packet in packets if packet.get("service") == "scheduler")["state"], "unavailable")
            self.assertNotIn("private-value", report.stdout + report.stderr)
            self.assertNotIn("private-id", report.stdout + report.stderr)
            self.assertNotIn("private-container-id", report.stdout + report.stderr)
            database = next(packet for packet in packets if "outbox" in packet)
            self.assertEqual(database["outbox"], {"pending": 3})
            for flag, expected in (("FIXTURE_DB_UNAVAILABLE", "database"), ("FIXTURE_SERVICE_UNAVAILABLE", "service")):
                with self.subTest(flag=flag):
                    cleanup.unlink()
                    failed_probe = subprocess.run(
                        ["sh", str(fixture / "tests/rehearsals/rehearse-live-workspace-e2e.sh")],
                        capture_output=True, text=True, check=False,
                        env={**os.environ, "PATH": str(fixture / "bin") + os.pathsep + os.environ["PATH"], "FIXTURE_CLEANUP": str(cleanup), flag: "1"},
                    )
                    self.assertEqual(failed_probe.returncode, 37)
                    self.assertTrue(cleanup.exists())
                    packets = [json.loads(line) for line in failed_probe.stderr.splitlines() if line.startswith('{')]
                    if expected == "database":
                        self.assertIn({"schema_version": 1, "database": "unavailable"}, packets)
                    else:
                        self.assertIn({"schema_version": 1, "service": "worker", "state": "unavailable"}, packets)
                    self.assertNotIn("private-container-id", failed_probe.stdout + failed_probe.stderr)


if __name__ == "__main__":
    unittest.main()
