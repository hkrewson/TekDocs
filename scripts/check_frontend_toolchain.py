"""Check coupled test tooling before expensive CI jobs start."""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REHEARSALS = (
    "rehearse-browser-e2e.sh",
    "rehearse-live-workspace-e2e.sh",
    "rehearse-browser-performance.sh",
)


def validate(root: Path) -> None:
    package = json.loads((root / "frontend/package.json").read_text())
    locked = json.loads((root / "frontend/package-lock.json").read_text())["packages"]
    versions = {}
    for name in ("vitest", "@vitest/coverage-v8", "@playwright/test"):
        version = package["devDependencies"][name]
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            raise ValueError(f"{name} requires an exact reviewed version")
        if (locked[""]["devDependencies"][name] != version
                or locked["node_modules/" + name]["version"] != version):
            raise ValueError(f"{name} manifest and lock must match")
        versions[name] = version
    if versions["vitest"] != versions["@vitest/coverage-v8"]:
        raise ValueError("Vitest and coverage-v8 must be updated together")
    playwright = versions["@playwright/test"]
    for name in ("playwright", "playwright-core"):
        if locked["node_modules/" + name]["version"] != playwright:
            raise ValueError("Playwright package chain must match")
    dockerfile = (root / "frontend/Dockerfile.e2e").read_text()
    if not re.search(r"^ARG PLAYWRIGHT_VERSION=" + re.escape(playwright) + r"$", dockerfile, re.M):
        raise ValueError("Playwright browser image version must match its package")
    if not re.search(r"^FROM mcr.microsoft.com/playwright:v\$\{PLAYWRIGHT_VERSION\}-noble@sha256:[0-9a-f]{64}(?: AS browser)?$", dockerfile, re.M):
        raise ValueError("Playwright browser image must retain its reviewed digest pin")
    for name in REHEARSALS:
        source = (root / "tests/rehearsals" / name).read_text()
        if (not re.search(r"^playwright_version=" + re.escape(playwright) + r"$", source, re.M)
                or f"'\"version\": \"{playwright}\"'" not in source):
            raise ValueError(f"{name} must use the matching Playwright version and assertion")


if __name__ == "__main__":
    try:
        validate(ROOT)
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(f"Frontend toolchain mismatch: {error}") from error
    print("Frontend test-toolchain versions and browser image pin agree.")
