from __future__ import annotations

import hashlib
from datetime import datetime
import io
import json
import zipfile
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_status import verify_local, verify_run
import release_status


class ReleaseStatusTests(unittest.TestCase):
    def test_single_push_requires_each_successful_exact_source_job(self):
        candidate = "a" * 40
        for workflow, names in release_status.SINGLE_PUSH_JOBS.items():
            jobs = [dict(name=name, head_sha=candidate, status="completed", conclusion="success")
                    for name in names]
            release_status.verify_single_push_jobs(jobs, candidate, workflow)
            for change in ({"conclusion": "skipped"}, {"conclusion": "failure"},
                           {"head_sha": "b" * 40}, {"status": "queued"}):
                with self.assertRaises(ValueError):
                    release_status.verify_single_push_jobs([dict(jobs[0], **change), *jobs[1:]], candidate, workflow)
            for invalid in (jobs[1:], [*jobs, jobs[0]]):
                with self.assertRaises(ValueError):
                    release_status.verify_single_push_jobs(invalid, candidate, workflow)

    def test_production_digests_match_exact_attempt_artifact(self):
        manifest = json.loads(
            (release_status.ROOT / ".github/release-candidate.json").read_text()
        )
        record = json.loads(
            (release_status.ROOT / manifest["security_record"]).read_text()
        )
        entry = next(
            e
            for e in record["evidence"]
            if e["category"] == "production_images_sbom_provenance"
        )
        run = {"id": manifest["workflows"]["Build, test, and secure"], "run_attempt": 1}
        artifact = {
            "id": 123,
            "name": f"tekdocs-security-evidence-production-images-{manifest['candidate_commit']}-1",
            "expired": False,
            "size_in_bytes": 1000,
        }
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("production-images.json", json.dumps(entry))
        with (
            patch.object(
                release_status, "gh_json", return_value={"artifacts": [artifact]}
            ),
            patch.object(release_status.subprocess, "run") as fetch,
        ):
            fetch.return_value.returncode = 0
            fetch.return_value.stdout = archive.getvalue()
            release_status.verify_production_evidence(
                entry, run, manifest["repository"], manifest["candidate_commit"]
            )
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                release_status.verify_production_evidence(
                    {**entry, "immutable_identifier": "sha256:" + "0" * 64},
                    run,
                    manifest["repository"],
                    manifest["candidate_commit"],
                )
        with patch.object(
            release_status,
            "gh_json",
            return_value={"artifacts": [{**artifact, "expired": True}]},
        ):
            with self.assertRaisesRegex(ValueError, "unavailable"):
                release_status.verify_production_evidence(
                    entry, run, manifest["repository"], manifest["candidate_commit"]
                )

    def test_hosted_identifiers_match_run_attempt_and_category(self):
        record = json.loads(
            (
                release_status.ROOT / "planning/releases/0.9.8-security-review.json"
            ).read_text()
        )
        manifest = {
            "schema_version": 1, "repository": "hkrewson/TekDocs",
            "candidate_commit": record["candidate_commit"],
            "security_record": "planning/releases/0.9.8-security-review.json",
            "workflows": {"Build, test, and secure": 38516198438,
                          "CodeQL": 38516198437, "Extended validation": 38516229558},
            "operator_acceptance": {"decision": "accepted",
                "reference": "planning/responsive-layouts/0.9.8-operator-acceptance.md"},
        }
        # Identity checks use the historical review's clock, not today's date.
        # Production inspection still uses the live clock and rejects expiry.
        reviewed_at = datetime.fromisoformat(record["completed_at"].replace("Z", "+00:00"))
        real_validate = release_status.validate_record
        self.enterContext(patch.object(
            release_status, "validate_record",
            side_effect=lambda data, **kwargs: real_validate(data, now=reviewed_at, **kwargs),
        ))
        original_loads = json.loads

        def replacement(raw, *args, **kwargs):
            parsed = original_loads(raw, *args, **kwargs)
            if isinstance(parsed, dict) and "private_report_reference" in parsed:
                return record
            return parsed

        def run(endpoint):
            # Unexpected calls must fail the test, not become a release blocker.
            self.assertIn(
                endpoint,
                {
                    f"repos/{manifest['repository']}/actions/runs/{run_id}"
                    for run_id in manifest["workflows"].values()
                },
            )
            run_id = int(endpoint.rsplit("/", 1)[1])
            return dict(
                id=run_id,
                run_attempt=1,
                head_sha=manifest["candidate_commit"],
                name=next(k for k, v in manifest["workflows"].items() if v == run_id),
                repository={"full_name": manifest["repository"]},
                status="completed",
                conclusion="success",
            )

        with (
            patch.object(release_status.json, "loads", side_effect=replacement),
            patch.object(release_status, "gh_json", side_effect=run),
            # Artifact verification has its own positive/mismatch/expiry tests.
            patch.object(release_status, "verify_production_evidence") as production,
        ):
            self.assertEqual(
                release_status.inspect(manifest, release_status.ROOT, True)["blockers"],
                [],
                "Valid identities must pass before exercising negative cases",
            )
            production.assert_called_once()

        for identifier in (
            "unrelated-run:999:missing-artifact",
            "38516229558:2:dast",
            "38516229558:1:supported-upgrades",
        ):
            with self.subTest(identifier=identifier):
                next(e for e in record["evidence"] if e["category"] == "dast")[
                    "immutable_identifier"
                ] = identifier
                with (
                    patch.object(release_status.json, "loads", side_effect=replacement),
                    patch.object(release_status, "gh_json", side_effect=run),
                    patch.object(release_status, "verify_production_evidence"),
                ):
                    self.assertIn(
                        "security evidence",
                        release_status.inspect(manifest, release_status.ROOT, True)[
                            "blockers"
                        ],
                    )

    def test_historical_exception_still_fails_at_expiry(self):
        record = json.loads((release_status.ROOT /
            "planning/releases/0.9.8-security-review.json").read_text())
        expires_at = datetime.fromisoformat(record["exceptions"][0]["expires_at"].replace("Z", "+00:00"))
        with self.assertRaisesRegex(ValueError, "exception TD-MAILPIT-XNET is expired"):
            release_status.validate_record(record,
                candidate_commit=record["candidate_commit"], now=expires_at)

    def test_retained_dependency_scan_requires_successful_job_and_exact_artifact(self):
        entry = {"category": "dependency_license_secret", "immutable_identifier": "42:1:security"}
        run = {"id": 42, "run_attempt": 2}
        job = {"name": "Dependency, license, code, and secret policy", "head_sha": "a" * 40,
               "status": "completed", "conclusion": "success"}
        with patch.object(release_status, "gh_json", return_value={"jobs": [job]}), patch.object(
            release_status, "verify_hosted_artifact", create=True
        ) as artifact:
            release_status.verify_retained_dependency(entry, run, "owner/repo", "a" * 40, 1)
            self.assertEqual(artifact.call_args.args[-1],
                "tekdocs-security-evidence-dependency-license-secret-" + "a" * 40 + "-1")
        for jobs in ([], [job, job], [{**job, "conclusion": "failure"}],
                     [{**job, "head_sha": "b" * 40}], [{**job, "status": "in_progress"}]):
            with self.subTest(jobs=jobs), patch.object(release_status, "gh_json", return_value={"jobs": jobs}):
                with self.assertRaises(ValueError):
                    release_status.verify_retained_dependency(entry, run, "owner/repo", "a" * 40, 1)
        with self.assertRaises(ValueError):
            release_status.verify_retained_dependency(entry, run, "owner/repo", "a" * 40, 3)
        with self.assertRaises(ValueError):
            release_status.verify_retained_dependency({**entry, "category": "dast"}, run, "owner/repo", "a" * 40, 1)

    def test_status_keeps_candidate_pinned_and_offline_runs_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "accepted.md").write_text(
                "Operator accepted current state; tests not inferred."
            )
            (root / "report.md").write_text("bounded review")
            digest = hashlib.sha256(b"bounded review").hexdigest()
            record = {
                "evidence": [
                    {
                        "category": "source_review",
                        "reference": "report.md",
                        "immutable_identifier": "sha256:" + digest,
                    }
                ],
                "private_report_reference": f"report.md (sha256:{digest})",
                "findings": [],
                "exceptions": [],
            }
            (root / "record.json").write_text(json.dumps(record))
            manifest = {
                "schema_version": 1,
                "candidate_commit": "a" * 40,
                "repository": "hkrewson/TekDocs",
                "security_record": "record.json",
                "workflows": {
                    "CodeQL": 1,
                    "Extended validation": 2,
                    "Build, test, and secure": 3,
                },
                "operator_acceptance": {
                    "decision": "accepted",
                    "reference": "accepted.md",
                },
            }
            # Structural record validation has its own exhaustive suite. Isolate
            # the new reference and online/offline orchestration boundary here.
            with (
                patch.object(release_status, "validate_record"),
                patch.object(release_status, "gh_json") as gh,
            ):
                result = release_status.inspect(manifest, root, False)
                self.assertEqual(result["candidate_commit"], "a" * 40)
                self.assertEqual(set(result["blockers"]), release_status.WORKFLOWS)
                gh.assert_not_called()
                record["evidence"] = [
                    {
                        "category": "dast",
                        "reference": "https://github.com/hkrewson/TekDocs/actions/runs/1",
                    }
                ]
                (root / "record.json").write_text(json.dumps(record))
                self.assertIn(
                    "security evidence",
                    release_status.inspect(manifest, root, False)["blockers"],
                )

    def test_local_evidence_requires_matching_bytes_and_safe_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.md").write_text("reviewed")
            digest = "sha256:" + hashlib.sha256(b"reviewed").hexdigest()
            verify_local(root, "report.md", digest)
            for path, checksum in [
                ("missing", digest),
                ("../report.md", digest),
                ("report.md", "sha256:" + "0" * 64),
            ]:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    verify_local(root, path, checksum)
            (root / "link").symlink_to(root / "report.md")
            with self.assertRaises(ValueError):
                verify_local(root, "link", digest)

    def test_run_must_match_repo_commit_workflow_and_success(self):
        valid = dict(
            head_sha="a" * 40,
            status="completed",
            conclusion="success",
            name="CodeQL",
            repository={"full_name": "hkrewson/TekDocs"},
        )
        verify_run(valid, "a" * 40, "CodeQL", "hkrewson/TekDocs")
        for key, value in [
            ("head_sha", "b" * 40),
            ("status", "in_progress"),
            ("conclusion", "failure"),
            ("name", "Unrelated"),
            ("repository", {"full_name": "elsewhere/repo"}),
        ]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_run(
                    {**valid, key: value}, "a" * 40, "CodeQL", "hkrewson/TekDocs"
                )
