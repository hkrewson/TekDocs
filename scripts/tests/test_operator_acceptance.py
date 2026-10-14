from __future__ import annotations

import sys
import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import operator_acceptance as acceptance
import recovery_preflight


class AcceptancePreparationTests(unittest.TestCase):
    def test_invalid_configuration_blocks_startup_and_seeding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "artifacts").mkdir()

            def run(args, **kwargs):
                return "a" * 40 if args[:3] == ["git", "rev-parse", "HEAD"] else ""

            with (
                patch.object(acceptance, "ROOT", root),
                patch.object(acceptance, "command", side_effect=run) as command,
                patch.object(
                    acceptance,
                    "validate_configuration",
                    side_effect=ValueError("unsafe configuration"),
                ),
                patch.object(acceptance, "fixture") as seed,
            ):
                with self.assertRaisesRegex(ValueError, "unsafe configuration"):
                    acceptance.prepare(root / "artifacts" / "test", 3312, 8112)
                seed.assert_not_called()
                self.assertFalse(
                    any("up" in call.args[0] for call in command.call_args_list)
                )

    def test_configuration_refuses_exposed_ports_egress_or_foreign_volumes(self):
        import copy

        state = {"project": "tekdocs_acceptance_012345abcdef"}
        config = {
            "name": state["project"],
            "services": {
                "frontend": {"ports": [{"host_ip": "127.0.0.1"}]},
                "backend": {"networks": {"internal": {}}},
            },
            "networks": {"internal": {"internal": True}},
            "volumes": {"data": {"name": state["project"] + "_data"}},
        }
        with (
            patch.object(acceptance, "compose", return_value=["docker", "compose"]),
            patch.object(acceptance, "command", return_value=json.dumps(config)),
        ):
            acceptance.validate_configuration(state, Path("unused"))
        for kind in ("port", "network", "volume"):
            bad = copy.deepcopy(config)
            if kind == "port":
                bad["services"]["frontend"]["ports"][0].pop("host_ip")
            elif kind == "network":
                bad["networks"]["internal"]["internal"] = False
            else:
                bad["volumes"]["data"]["name"] = "production_data"
            with (
                self.subTest(kind=kind),
                patch.object(acceptance, "compose", return_value=["docker", "compose"]),
                patch.object(acceptance, "command", return_value=json.dumps(bad)),
            ):
                with self.assertRaises(ValueError):
                    acceptance.validate_configuration(state, Path("unused"))

    def test_commands_do_not_inherit_application_or_compose_overrides(self):
        with (
            patch.dict(
                os.environ,
                {
                    "TEKDOCS_PORT": "3311",
                    "POSTGRES_OWNER_PASSWORD": "conflicting-test-value",
                    "COMPOSE_PROFILES": "production",
                },
            ),
            patch.object(acceptance.subprocess, "run") as run,
        ):
            run.return_value.returncode = 0
            run.return_value.stdout = ""
            acceptance.command(["docker", "compose", "version"])
            child = run.call_args.kwargs.get("env", os.environ)
            for key in ("TEKDOCS_PORT", "POSTGRES_OWNER_PASSWORD", "COMPOSE_PROFILES"):
                self.assertFalse(key in child, f"unsafe inherited variable: {key}")

    def test_failure_triage_covers_every_other_job(self):
        import re

        source = (
            (acceptance.ROOT / ".github/workflows/extended-validation.yml")
            .read_text()
            .split("jobs:\n", 1)[1]
        )
        jobs = set(re.findall(r"^  ([a-z][a-z-]+):$", source, re.M))
        needs = set(
            re.search(r"needs: \[([^]]+)\]", source)[1].replace(" ", "").split(",")
        )
        self.assertEqual(needs, jobs - {"failure-triage"})

    def test_networkless_renderer_is_isolated_but_normal_bridge_is_not(self):
        self.assertTrue(
            acceptance.isolated_network({"Internal": False, "Driver": "null"})
        )
        self.assertTrue(
            acceptance.isolated_network({"Internal": True, "Driver": "bridge"})
        )
        self.assertFalse(
            acceptance.isolated_network({"Internal": False, "Driver": "bridge"})
        )
        self.assertFalse(acceptance.isolated_network({}))

    def test_prepare_generates_loopback_binding_and_shared_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "artifacts").mkdir()
            directory = root / "artifacts" / "new"

            def fake_command(args, **kwargs):
                if args[:3] == ["git", "rev-parse", "HEAD"]:
                    return "a" * 40
                return ""

            with (
                patch.object(acceptance, "ROOT", root),
                patch.object(acceptance, "command", side_effect=fake_command),
                patch.object(acceptance, "fixture"),
                patch.object(acceptance, "doctor"),
                patch.object(acceptance, "validate_configuration"),
            ):
                acceptance.prepare(directory, 3310, 8110)
            self.assertIn(
                "TEKDOCS_PORT=127.0.0.1:3310", (directory / "local.env").read_text()
            )
            overlay = json.loads((directory / "compose.json").read_text())
            self.assertTrue(overlay["networks"]["internal"]["internal"])
            self.assertIn(
                "media_data:/app/media", overlay["services"]["migrate"]["volumes"]
            )

    def test_fixture_steps_share_runtime_file_storage(self):
        self.assertIn("media_data:/app/media", acceptance.FIXTURE_VOLUMES)
        self.assertIn("diagram_jobs:/app/diagram-jobs", acceptance.FIXTURE_VOLUMES)

    def test_down_stack_invalidates_previous_readiness_without_seeding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "artifacts" / "acceptance-test"
            directory.mkdir(parents=True, mode=0o700)
            (directory / "readiness.json").write_text('{"ready":true}')
            state = dict(
                project="tekdocs_acceptance_012345abcdef",
                source_commit="a" * 40,
                port=3298,
                mail_port=8098,
            )
            with (
                patch.object(acceptance, "ROOT", root),
                patch.object(acceptance, "command", return_value=""),
                patch.object(acceptance, "fixture") as seed,
            ):
                with self.assertRaisesRegex(ValueError, "stack is down"):
                    acceptance.doctor(state, directory)
                seed.assert_not_called()
            self.assertFalse(
                json.loads((directory / "readiness.json").read_text())["ready"]
            )

    def test_state_rejects_foreign_project_unsafe_ports_and_public_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "artifacts" / "acceptance-test"
            directory.mkdir(parents=True, mode=0o700)
            state = dict(
                project="tekdocs_acceptance_012345abcdef",
                source_commit="a" * 40,
                port=3298,
                mail_port=8098,
            )
            with patch.object(acceptance, "ROOT", root):
                acceptance.validate_state(state, directory)
                for key, value in [
                    ("project", "tekdocs"),
                    ("port", 80),
                    ("mail_port", 3298),
                    ("source_commit", "main"),
                ]:
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        acceptance.validate_state({**state, key: value}, directory)
                directory.chmod(0o755)
                with self.assertRaises(ValueError):
                    acceptance.validate_state(state, directory)

    def test_existing_destination_is_never_reseeded(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(acceptance, "command") as run,
        ):
            with self.assertRaisesRegex(ValueError, "destination exists"):
                acceptance.prepare(Path(temporary), 3298, 8098)
            run.assert_not_called()

    def test_verifier_does_not_create_accounts_or_change_assignments(self):
        source = (acceptance.FIXTURES / "verify.py").read_text()
        for mutation in ("create_user", ".save(", ".create(", ".open('a')"):
            self.assertNotIn(mutation, source)

    def test_recovery_preflight_refuses_failed_mount_and_low_space(self):
        for code, stdout in [(1, ""), (0, "1024"), (0, "invalid")]:
            with patch.object(recovery_preflight.subprocess, "run") as run:
                run.return_value.returncode, run.return_value.stdout = code, stdout
                with self.assertRaises(ValueError):
                    recovery_preflight.preflight()

    def test_both_recovery_rehearsals_preflight_before_startup(self):
        for name in (
            "rehearse-supported-recovery.sh",
            "rehearse-repository-foundation.sh",
        ):
            source = (acceptance.ROOT / "tests/rehearsals" / name).read_text()
            self.assertLess(
                source.index("recovery_preflight.py"),
                source.index("work_directory=$(mktemp"),
            )
