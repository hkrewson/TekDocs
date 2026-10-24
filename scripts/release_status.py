"""Read-only, explicit-candidate release summary. Never dispatches or publishes."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path

from check_automated_security_review import COMMIT_PATTERN, validate_record

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {"Build, test, and secure", "CodeQL", "Extended validation"}
SINGLE_PUSH_JOBS = {
    "CodeQL": {"release-codeql / analyze (python)",
               "release-codeql / analyze (javascript-typescript)",
               "release-codeql / CodeQL evidence"},
    "Extended validation": {
        "release-extended / Supported upgrade matrix",
        "release-extended / Supported backup and restore",
        "release-extended / Dynamic application security test",
        "release-extended / Public-beta performance reference",
        "release-extended / Browser security evidence",
        "release-extended / Diagram upgrade and restore evidence",
        *{f"release-extended / Browser ({browser})" for browser in
          ("chromium", "firefox", "webkit", "mobile-chromium", "mobile-webkit")},
    },
    "Build, test, and secure": {"Publish tested production images",
                                "Production containers, SBOMs, and vulnerability scan"},
}


def verify_single_push_jobs(jobs: list[dict], candidate: str, workflow: str) -> None:
    for name in SINGLE_PUSH_JOBS[workflow]:
        matching = [job for job in jobs if job.get("name") == name]
        if len(matching) != 1 or any(matching[0].get(key) != value for key, value in {
            "head_sha": candidate, "status": "completed", "conclusion": "success",
        }.items()):
            raise ValueError("required release job missing, skipped, failed or wrong source")
EVIDENCE_SCOPES = {
    "authorization_and_rls": "runtime+postgres-shards",
    "backup_and_restore": "supported-recovery",
    "browser_security": "chromium+firefox+webkit+mobile",
    "codeql": "python+javascript-typescript",
    "dast": "dast",
    "dependency_license_secret": "security",
    "image_scan": "backend+frontend+renderer+mailpit",
    "upgrade": "supported-upgrades",
}
CATEGORY_WORKFLOW = {
    "codeql": "CodeQL",
    **dict.fromkeys(
        [
            "authorization_and_rls",
            "dependency_license_secret",
            "image_scan",
            "production_images_sbom_provenance",
        ],
        "Build, test, and secure",
    ),
    **dict.fromkeys(
        ["browser_security", "backup_and_restore", "upgrade", "dast"],
        "Extended validation",
    ),
}


def local_path(root: Path, reference: str) -> Path:
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("evidence path must remain repository-relative")
    root = root.resolve()
    path = root / relative
    parents = [
        root / Path(*relative.parts[:n]) for n in range(1, len(relative.parts) + 1)
    ]
    if any(part.is_symlink() for part in parents) or not path.is_file():
        raise ValueError("evidence file missing or symlinked")
    return path


def verify_local(root: Path, reference: str, identifier: str) -> None:
    path = local_path(root, reference)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", identifier):
        raise ValueError("local evidence requires an exact SHA-256 identifier")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != identifier[7:]:
        raise ValueError("local evidence digest mismatch")


def verify_run(run: dict, candidate: str, workflow: str, repository: str) -> None:
    if (
        run.get("head_sha") != candidate
        or run.get("name") != workflow
        or run.get("repository", {}).get("full_name") != repository
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
    ):
        raise ValueError("run has wrong scope, is unfinished, or did not pass")


def gh_json(endpoint: str):
    result = subprocess.run(
        ["gh", "api", endpoint], capture_output=True, text=True, timeout=45
    )
    if result.returncode:
        raise ValueError("GitHub verification unavailable; no cached pass substituted")
    return json.loads(result.stdout)


def verify_production_evidence(
    entry: dict, run: dict, repository: str, candidate: str
) -> None:
    # Production evidence uses image digests rather than run:attempt identifiers.
    # Compare those digests with the exact run/attempt's retained evidence.
    expected = (
        f"tekdocs-security-evidence-production-images-{candidate}-{run['run_attempt']}"
    )
    verify_hosted_artifact(entry, run, repository, expected)


def verify_retained_dependency(
    entry: dict, run: dict, repository: str, candidate: str, attempt: int
) -> None:
    # Partial reruns retain successful jobs. Accept only this explicitly supported
    # category, with its successful exact-source job and original artifact bytes.
    if (
        entry["category"] != "dependency_license_secret"
        or not 1 <= attempt < run["run_attempt"]
    ):
        raise ValueError("unsupported retained evidence attempt")
    jobs, page = [], 1
    while True:
        batch = gh_json(
            f"repos/{repository}/actions/runs/{run['id']}/attempts/{attempt}/jobs?per_page=100&page={page}"
        )["jobs"]
        jobs.extend(
            job for job in batch
            if job.get("name") == "Dependency, license, code, and secret policy"
        )
        if len(batch) < 100:
            break
        page += 1
    expected_job = {
        "head_sha": candidate, "status": "completed", "conclusion": "success"
    }
    if len(jobs) != 1 or any(
        jobs[0].get(key) != value for key, value in expected_job.items()
    ):
        raise ValueError("retained dependency job missing, ambiguous, failed or wrong source")
    expected = f"tekdocs-security-evidence-dependency-license-secret-{candidate}-{attempt}"
    verify_hosted_artifact(entry, run, repository, expected)


def verify_hosted_artifact(entry: dict, run: dict, repository: str, expected: str) -> None:
    artifacts, page = [], 1
    while True:
        batch = gh_json(
            f"repos/{repository}/actions/runs/{run['id']}/artifacts?per_page=100&page={page}"
        )["artifacts"]
        artifacts.extend(
            a for a in batch if a.get("name") == expected and not a.get("expired")
        )
        if len(batch) < 100:
            break
        page += 1
    if len(artifacts) != 1:
        raise ValueError("production evidence artifact unavailable or ambiguous")
    artifact_id = artifacts[0]["id"]
    if (
        type(artifact_id) is not int
        or artifacts[0].get("size_in_bytes", 0) > 1024 * 1024
    ):
        raise ValueError("invalid production evidence artifact")
    result = subprocess.run(
        ["gh", "api", f"repos/{repository}/actions/artifacts/{artifact_id}/zip"],
        capture_output=True,
        timeout=45,
    )
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise ValueError("production evidence download unavailable")
    try:
        with zipfile.ZipFile(io.BytesIO(result.stdout)) as archive:
            members = archive.infolist()
            if len(members) != 1 or members[0].file_size > 1024 * 1024:
                raise ValueError("unexpected evidence archive contents")
            hosted = json.loads(archive.read(members[0]))
    except (zipfile.BadZipFile, UnicodeError) as error:
        raise ValueError("invalid evidence archive") from error
    if not isinstance(hosted, dict):
        raise ValueError("invalid production evidence record")
    if hosted != entry:
        raise ValueError("hosted evidence identity mismatch")


def inspect(manifest: dict, root: Path, online: bool) -> dict:
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported release manifest")
    candidate = manifest["candidate_commit"]
    if not COMMIT_PATTERN.fullmatch(candidate):
        raise ValueError("candidate must be an exact SHA, never implicit HEAD")
    repository = manifest["repository"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("invalid repository")
    workflows = manifest["workflows"]
    if set(workflows) != WORKFLOWS:
        raise ValueError("manifest must name all three required workflows")
    pipeline = manifest.get("pipeline", "separate_workflows")
    if pipeline not in {"separate_workflows", "single_push"}:
        raise ValueError("unsupported release pipeline")
    if pipeline == "single_push" and len(set(workflows.values())) != 1:
        raise ValueError("single-push evidence must use one release run")
    blockers, checks, verified_runs = [], {}, {}
    release_jobs = None
    for name, run_id in workflows.items():
        if type(run_id) is not int or run_id <= 0:
            raise ValueError("workflow run IDs must be positive integers")
        checks[name] = "unverified (use --online)"
        if online:
            try:
                run = gh_json(f"repos/{repository}/actions/runs/{run_id}")
                verify_run(run, candidate, "Build, test, and secure" if pipeline == "single_push" else name, repository)
                if pipeline == "single_push":
                    if run.get("event") != "push" or run.get("head_branch") != "main":
                        raise ValueError("release must be a main push")
                    if release_jobs is None:
                        release_jobs, page = [], 1
                        while True:
                            batch = gh_json(f"repos/{repository}/actions/runs/{run_id}/attempts/{run['run_attempt']}/jobs?per_page=100&page={page}")["jobs"]
                            release_jobs.extend(batch)
                            if len(batch) < 100:
                                break
                            page += 1
                    verify_single_push_jobs(release_jobs, candidate, name)
                verified_runs[str(run_id)] = run
                checks[name] = "passed"
            except (ValueError, subprocess.TimeoutExpired):
                checks[name] = "blocked or unavailable"
        if checks[name] != "passed":
            blockers.append(name)
    record = None
    try:
        record = json.loads(local_path(root, manifest["security_record"]).read_text())
        validate_record(record, candidate_commit=candidate)
        for entry in record["evidence"]:
            reference = entry["reference"]
            if reference.startswith("https://"):
                match = re.fullmatch(
                    rf"https://github.com/{re.escape(repository)}/actions/runs/([0-9]+)",
                    reference,
                )
                if not match or match[1] not in {str(n) for n in workflows.values()}:
                    raise ValueError("evidence references an unlisted run")
                expected = CATEGORY_WORKFLOW.get(entry["category"])
                if expected is None or str(workflows[expected]) != match[1]:
                    raise ValueError("evidence category references the wrong workflow")
                if online and match[1] not in verified_runs:
                    raise ValueError("evidence run has not passed verification")
                category = entry["category"]
                if category in EVIDENCE_SCOPES:
                    identity = re.fullmatch(
                        r"([0-9]+):([1-9][0-9]*):(.+)", entry["immutable_identifier"]
                    )
                    if (
                        not identity
                        or identity[1] != match[1]
                        or identity[3] != EVIDENCE_SCOPES[category]
                    ):
                        raise ValueError(
                            "hosted evidence identifier has wrong run or category"
                        )
                    if (
                        online
                        and int(identity[2]) != verified_runs[match[1]]["run_attempt"]
                    ):
                        verify_retained_dependency(
                            entry, verified_runs[match[1]], repository, candidate, int(identity[2])
                        )
                elif online:
                    verify_production_evidence(
                        entry, verified_runs[match[1]], repository, candidate
                    )
            else:
                if entry["category"] != "source_review":
                    raise ValueError("hosted categories require hosted run evidence")
                verify_local(root, reference, entry["immutable_identifier"])
        report = record["private_report_reference"]
        match = re.fullmatch(r"(.+) \(sha256:([0-9a-f]{64})\)", report)
        if not match:
            raise ValueError("private report needs a path and SHA-256")
        verify_local(root, match[1], "sha256:" + match[2])
        checks["security evidence"] = "verified locally; hosted checks above"
    except (OSError, ValueError, KeyError, TypeError):
        record = None
        checks["security evidence"] = (
            "blocked: missing, invalid, expired or altered evidence"
        )
        blockers.append("security evidence")
    acceptance = manifest.get("operator_acceptance", {})
    if acceptance.get("decision") != "accepted" or not acceptance.get("reference"):
        blockers.append("operator decision")
    else:
        local_path(root, acceptance["reference"])
    return {
        "candidate_commit": candidate,
        "checks": checks,
        "blockers": blockers,
        "operator_acceptance": acceptance,
        "remaining_release_actions": manifest.get("remaining_release_actions", []),
        "exception_deadlines": (
            [item["expires_at"] for item in record.get("exceptions", [])]
            + [
                item["acceptance"]["review_at"]
                for item in record.get("findings", [])
                if item.get("status") == "accepted"
            ]
        )
        if record
        else [],
        "scope": "Status only; evidence is not an independent audit or permission to release.",
        "artifact_provenance": "Production evidence and retained earlier-attempt dependency evidence compared with hosted artifact bytes when online; other artifact contents are not independently authenticated.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / ".github/release-candidate.json"
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="Verify pinned run identities with read-only GitHub API",
    )
    args = parser.parse_args()
    try:
        result = inspect(json.loads(args.manifest.read_text()), ROOT, args.online)
        print(json.dumps(result, indent=2))
        return int(bool(result["blockers"]))
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        print(
            "Release status unavailable: invalid manifest, unavailable evidence or verification dependency."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
