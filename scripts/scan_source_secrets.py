"""Scan Git-visible working source without copying private ignored runtime data."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "zricethezav/gitleaks:latest@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"


def export_sources(root: Path, destination: Path) -> int:
    root = root.resolve()
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    ).split(b"\0")
    count = 0
    for raw in paths:
        if not raw:
            continue
        relative = Path(raw.decode("utf-8", errors="surrogateescape"))
        source = root / relative
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError("Source scan refuses symbolic links or paths outside the repository")
        if not source.exists():
            continue  # A tracked deletion is not part of the working source.
        if not source.is_file():
            raise ValueError("Source scan requires regular source files")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        count += 1
    return count


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="tekdocs-source-secrets-") as directory:
        destination = Path(directory)
        count = export_sources(ROOT, destination)
        print(f"Scanning {count} Git-visible working source files; ignored runtime data is excluded.", flush=True)
        return subprocess.run(
            ["docker", "run", "--rm", "-v", f"{destination}:/src:ro", IMAGE,
             "detect", "--source=/src", "--no-git", "--no-banner", "--redact"],
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
