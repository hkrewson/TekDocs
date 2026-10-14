import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci_status import summarize


class CompactCITests(unittest.TestCase):
    def test_untracked_failure_has_owner_and_cannot_be_mistaken_for_success(self):
        run = dict(id=12, head_sha="a" * 40, status="completed", conclusion="failure")
        jobs = [
            dict(name="Recovery", conclusion="failure"),
            dict(name="Browser", conclusion="success"),
        ]
        ledger = dict(default_owner="maintainer", failures=[])
        result = summarize(run, jobs, ledger)
        self.assertEqual(
            result["failures"],
            [
                dict(
                    job="Recovery",
                    conclusion="failure",
                    owner="maintainer",
                    triage="required",
                )
            ],
        )
        ledger["failures"].append(
            dict(
                run_id=12,
                job="Recovery",
                owner="maintainer",
                reproduction="make supported-recovery-rehearsal",
                cause="unknown",
                next_action="reproduce",
            )
        )
        self.assertEqual(
            summarize(run, jobs, ledger)["failures"][0]["triage"], "tracked"
        )
        self.assertEqual(summarize(run, jobs, ledger)["conclusion"], "failure")
