"""Opt-in read-only probes against a prepared disposable acceptance stack.

TEKDOCS_ACCEPTANCE_TEST_DIRECTORY=artifacts/<prepared> python3 -m unittest
scripts/tests/test_acceptance_live.py -v
"""

import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import operator_acceptance as acceptance


@unittest.skipUnless(
    os.environ.get("TEKDOCS_ACCEPTANCE_TEST_DIRECTORY"),
    "requires prepared disposable stack",
)
class LiveAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(
            os.environ["TEKDOCS_ACCEPTANCE_TEST_DIRECTORY"]
        ).absolute()
        self.state = json.loads((self.directory / "state.json").read_text())
        acceptance.validate_state(self.state, self.directory)

    def test_conflicting_shell_does_not_change_resolved_configuration(self):
        from unittest.mock import patch

        with patch.dict(
            os.environ,
            {
                "TEKDOCS_PORT": "3311",
                "POSTGRES_OWNER_PASSWORD": "not-a-real-secret",
                "COMPOSE_PROFILES": "production",
            },
        ):
            acceptance.validate_configuration(self.state, self.directory)
            config = json.loads(
                acceptance.command(
                    acceptance.compose(self.state, self.directory)
                    + ["config", "--format", "json"]
                )
            )
        port = config["services"]["frontend"]["ports"][0]
        self.assertEqual(port["host_ip"], "127.0.0.1")
        self.assertEqual(int(port["published"]), self.state["port"])
        self.assertFalse(
            config["services"]["db"]["environment"]["POSTGRES_PASSWORD"]
            == "not-a-real-secret"
        )

    def test_current_publication_checks_reject_withdrawn_or_missing_retained_pdf(self):
        source = (acceptance.FIXTURES / "verify.py").read_text()
        for target, options in [
            (
                "apps.core.repository_static_delivery.repository_static_state",
                "return_value='withdrawn'",
            ),
            (
                "django.core.files.storage.FileSystemStorage.open",
                "side_effect=FileNotFoundError('simulated unavailable storage')",
            ),
        ]:
            with self.subTest(target=target):
                probe = (
                    "from unittest.mock import patch\nfrom django.http import Http404\n"
                    f"with patch({target!r}, {options}):\n"
                    "    try:\n"
                    f"        exec(compile({source!r}, 'verify.py', 'exec'))\n"
                    "    except Http404:\n"
                    "        print('EXPECTED_PUBLICATION_UNAVAILABLE')\n"
                    "    else:\n"
                    "        raise RuntimeError('readiness accepted unavailable publication')\n"
                )
                args = acceptance.compose(self.state, self.directory) + [
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "-e",
                    "TEKDOCS_ACCEPTANCE_FIXTURE=isolated-disposable",
                    "-e",
                    f"TEKDOCS_ACCEPTANCE_URL=http://localhost:{self.state['port']}",
                    "--entrypoint",
                    "python",
                    "migrate",
                    "manage.py",
                    "shell",
                ]
                self.assertIn(
                    "EXPECTED_PUBLICATION_UNAVAILABLE",
                    acceptance.command(args, input=probe),
                )

    def test_live_readiness_remains_usable_without_reseeding(self):
        acceptance.doctor(self.state, self.directory)
        self.assertTrue(
            json.loads((self.directory / "readiness.json").read_text())["ready"]
        )
