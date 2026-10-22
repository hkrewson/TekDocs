"""Verify published images and atomically deliver application/receipt Git tags.

Run only in the trusted main-push publication job, after every validation gate.
The companion tag avoids changing the application SHA or creating another CI push.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

IMAGES = {
    "backend": "tekdocs-backend", "frontend": "tekdocs-frontend",
    "renderer": "tekdocs-diagram-renderer", "mailpit": "tekdocs-mailpit",
}


def run(*args: str, input: str | None = None, env: dict | None = None) -> str:
    return subprocess.check_output(args, text=True, input=input, env=env).strip()


def remote_tag(tag: str) -> str:
    result = run("git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}")
    return result.split()[0] if result else ""


def publish_commit_images() -> None:
    """Never replace a commit image on a full rerun with a different build."""
    sha = os.environ["GITHUB_SHA"]
    if (os.environ["GITHUB_EVENT_NAME"] != "push"
            or os.environ["GITHUB_REF"] != "refs/heads/main"
            or os.environ["GITHUB_REPOSITORY"] != "hkrewson/TekDocs"
            or not re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise ValueError("Image publication requires a trusted main push")
    missing = []
    for image in IMAGES.values():
        reference = "ghcr.io/hkrewson/" + image + ":sha-" + sha
        result = subprocess.run(["docker", "buildx", "imagetools", "inspect", reference, "--raw"],
                                text=True, capture_output=True)
        if result.returncode == 0:
            local_config = run("docker", "image", "inspect", reference, "--format", "{{.Id}}")
            if json.loads(result.stdout).get("config", {}).get("digest") != local_config:
                raise ValueError("Commit image already has another build; retry retained images or use a new version: " + image)
        elif "manifest unknown" in result.stderr.lower() or "not found" in result.stderr.lower():
            missing.append(reference)
        else:
            raise ValueError("Could not establish commit image state: " + image + ": " + result.stderr)
    for reference in missing:
        run("docker", "push", reference)


def finalize() -> None:
    sha, ref = os.environ["GITHUB_SHA"], os.environ["GITHUB_REF"]
    version = Path("VERSION").read_text().strip()
    if (os.environ["GITHUB_EVENT_NAME"] != "push" or ref != "refs/heads/main"
            or os.environ["GITHUB_REPOSITORY"] != "hkrewson/TekDocs"
            or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)):
        raise ValueError("Release requires a versioned trusted main push")
    tag = "v" + version
    existing = remote_tag(tag)
    if existing and existing != sha:
        raise ValueError("Release version already belongs to another commit")
    output = Path("artifacts/release")
    output.mkdir(parents=True, exist_ok=True)
    rows = ["commit=" + sha]
    verified = {}
    for name, image in IMAGES.items():
        repository = "ghcr.io/hkrewson/" + image
        digest = os.environ[name.upper() + "_DIGEST"]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("Invalid digest for " + name)
        immutable = repository + "@" + digest
        actual = run("docker", "buildx", "imagetools", "inspect",
                     repository + ":sha-" + sha, "--format", "{{json .Manifest.Digest}}")
        if json.loads(actual) != digest:
            raise ValueError("Published digest mismatch: " + name)
        for kind, predicate in [("provenance", "https://slsa.dev/provenance/v1"),
                                ("sbom", "https://cyclonedx.org/bom")]:
            result = run("gh", "attestation", "verify", "oci://" + immutable,
                         "--repo", "hkrewson/TekDocs", "--signer-workflow",
                         "hkrewson/TekDocs/.github/workflows/build.yml",
                         "--source-digest", sha, "--source-ref", ref,
                         "--deny-self-hosted-runners", "--predicate-type", predicate,
                         "--format", "json")
            if not json.loads(result):
                raise ValueError("Empty attestation verification: " + name)
            (output / f"{name}-{kind}.json").write_text(result + "\n")
        rows.append(name + "=" + immutable)
        verified[name] = immutable

    # Inspect existing aliases before writing any; never silently repoint a release.
    # The prepare job and release concurrency serialize normal writers. A retry must
    # retain the same digests, including after a partial publication failure.
    for name, image in IMAGES.items():
        repository = "ghcr.io/hkrewson/" + image
        result = subprocess.run(["docker", "buildx", "imagetools", "inspect",
                                 repository + ":" + version, "--format",
                                 "{{json .Manifest.Digest}}"], text=True, capture_output=True)
        if result.returncode == 0:
            if json.loads(result.stdout) != verified[name].split("@", 1)[1]:
                raise ValueError("Existing release image differs: " + name)
        elif "manifest unknown" not in result.stderr.lower() and "not found" not in result.stderr.lower():
            raise ValueError("Could not establish release alias state: " + name + ": " + result.stderr)
    for name, image in IMAGES.items():
        repository = "ghcr.io/hkrewson/" + image
        # Use loaded, tested images; docker tag/push retains the single-image digest.
        run("docker", "tag", repository + ":sha-" + sha, repository + ":" + version)
        run("docker", "push", repository + ":" + version)
        actual = run("docker", "buildx", "imagetools", "inspect", repository + ":" + version,
                     "--format", "{{json .Manifest.Digest}}")
        if json.loads(actual) != verified[name].split("@", 1)[1]:
            raise ValueError("Release alias verification failed: " + name)

    receipt = "\n".join(rows) + "\n"
    receipt_path = "scripts/releases/" + tag + ".images"
    (output / (tag + ".images")).write_text(receipt)
    companion = "receipts/" + tag
    existing_receipt = remote_tag(companion)
    if existing_receipt:
        run("git", "fetch", "origin", "refs/tags/" + companion)
        if (run("git", "show", "FETCH_HEAD:" + receipt_path) != receipt.strip()
                or run("git", "rev-parse", "FETCH_HEAD^") != sha):
            raise ValueError("Existing receipt tag differs from verified release")
        receipt_commit = existing_receipt
    else:
        # A separate index preserves the checkout. The receipt commit has exactly
        # one parent: the validated application. No source-branch commit is pushed.
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, GIT_INDEX_FILE=directory + "/index",
                       GIT_AUTHOR_NAME="github-actions[bot]", GIT_COMMITTER_NAME="github-actions[bot]",
                       GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
                       GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com")
            run("git", "read-tree", sha, env=env)
            blob = run("git", "hash-object", "-w", "--stdin", input=receipt)
            run("git", "update-index", "--add", "--cacheinfo", "100644," + blob + "," + receipt_path, env=env)
            tree = run("git", "write-tree", env=env)
            receipt_commit = run("git", "commit-tree", tree, "-p", sha,
                                 input="Verified release receipt for " + tag + "\n", env=env)
    run("git", "push", "--atomic", "origin", sha + ":refs/tags/" + tag,
        receipt_commit + ":refs/tags/" + companion)
    summary = {"release": tag, "candidate_commit": sha, "receipt_commit": receipt_commit,
               "source_ref": ref, "images": verified,
               "run": os.environ["GITHUB_SERVER_URL"] + "/" + os.environ["GITHUB_REPOSITORY"]
                      + "/actions/runs/" + os.environ["GITHUB_RUN_ID"]}
    (output / "release.json").write_text(json.dumps(summary, indent=2) + "\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(f"\n## Release {tag} complete\n\nFour images and eight attestations verified. "
                     f"Application and receipt tags delivered atomically.\n\n"
                     f"Update: `scripts/update-production.sh --release {tag}`\n")


if __name__ == "__main__":
    if sys.argv[1:] == ["--publish-images"]:
        publish_commit_images()
    elif not sys.argv[1:]:
        finalize()
    else:
        raise SystemExit("usage: finalize_ci_release.py [--publish-images]")
