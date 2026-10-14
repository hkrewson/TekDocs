"""Cheap Linux bind-mount and Docker-storage checks before recovery rehearsals."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def preflight() -> None:
    image = re.search(r"image: (postgres:[^\s]+)", (ROOT / "compose.yml").read_text())[
        1
    ]
    with tempfile.TemporaryDirectory(prefix="tekdocs-recovery-preflight-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        key = root / "synthetic-key"
        key.write_text("synthetic-preflight-only\n")
        key.chmod(0o444)
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--user",
                "10001:10001",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--mount",
                f"type=bind,src={key},dst=/fixture-key,readonly",
                image,
                "sh",
                "-c",
                "test -r /fixture-key && test ! -w /fixture-key && df -Pk / | tail -1 | awk '{print $4}'",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode or not result.stdout.strip().isdigit():
            raise ValueError("Linux service-scoped read-only key mount failed")
        if int(result.stdout.strip()) < 2 * 1024 * 1024:
            raise ValueError(
                "Docker filesystem has under 2 GiB free; inspect storage before recovery"
            )
        if root.stat().st_mode & 0o077:
            raise ValueError("private host-directory custody changed")


if __name__ == "__main__":
    try:
        preflight()
        print(
            "Recovery preflight passed: Linux key mount and minimum Docker free space. Not full capacity assurance."
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"Recovery preflight blocked: {error}")
        raise SystemExit(1)
