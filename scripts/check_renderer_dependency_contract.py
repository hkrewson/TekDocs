#!/usr/bin/env python3
"""Validate and record the dependency contract for Mermaid preview and export."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "tekdocs-renderer-dependency-contract/v1"
EXACT_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
CHROMIUM_SERIES = re.compile(r"^ARG CHROMIUM_SERIES=([0-9]+)$", re.MULTILINE)
PINNED_NODE_IMAGE = re.compile(r"^FROM node:[^\s]+@sha256:[0-9a-f]{64}$", re.MULTILINE)

CONTRACT_FILES = (
    "frontend/package.json",
    "frontend/package-lock.json",
    "renderer/package.json",
    "renderer/package-lock.json",
    "renderer/Dockerfile",
    "renderer/mermaid-config.json",
    "renderer/puppeteer-config.json",
    "renderer/worker.mjs",
)

REQUIRED_GATES = (
    "renderer dependency and license audit",
    "diagram export regression suite",
    "production image rehearsal",
    "renderer SBOM and vulnerability scan",
)


class ContractError(ValueError):
    """A renderer dependency contract invariant was not met."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"{path}: expected readable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path}: expected a JSON object")
    return value


def nested_string(document: dict[str, Any], path: str, *keys: str) -> str:
    value: Any = document
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise ContractError(f"{path}: missing {'.'.join(keys)}")
        value = value[key]
    if not isinstance(value, str) or not value:
        raise ContractError(f"{path}: {'.'.join(keys)} must be a non-empty string")
    return value


def exact_version(value: str, label: str) -> str:
    if not EXACT_VERSION.fullmatch(value):
        raise ContractError(f"{label} must use an exact semantic version; found {value!r}")
    return value


def matching_versions(label: str, versions: dict[str, str]) -> str:
    distinct = set(versions.values())
    if len(distinct) != 1:
        rendered = ", ".join(f"{source}={version}" for source, version in versions.items())
        raise ContractError(f"{label} versions must match: {rendered}")
    return next(iter(distinct))


def sha256(path: Path) -> str:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"{path}: could not read contract file: {exc}") from exc
    return hashlib.sha256(content).hexdigest()


def validate_dependabot(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"{path}: could not read dependency update policy: {exc}") from exc
    for ecosystem, directory in (("npm", "/frontend"), ("npm", "/renderer"), ("docker", "/renderer")):
        pattern = re.compile(
            rf"package-ecosystem:\s*{re.escape(ecosystem)}\s+directory:\s*{re.escape(directory)}(?:\s|$)",
            re.MULTILINE,
        )
        if not pattern.search(text):
            raise ContractError(f"{path}: missing {ecosystem} update policy for {directory}")


def build_contract(root: Path) -> dict[str, Any]:
    renderer_package = read_json(root / "renderer/package.json")
    renderer_lock = read_json(root / "renderer/package-lock.json")
    frontend_package = read_json(root / "frontend/package.json")
    frontend_lock = read_json(root / "frontend/package-lock.json")

    cli = matching_versions(
        "Mermaid CLI",
        {
            "renderer/package.json": exact_version(
                nested_string(renderer_package, "renderer/package.json", "dependencies", "@mermaid-js/mermaid-cli"),
                "renderer/package.json Mermaid CLI",
            ),
            "renderer lock root": nested_string(
                renderer_lock,
                "renderer/package-lock.json",
                "packages",
                "",
                "dependencies",
                "@mermaid-js/mermaid-cli",
            ),
            "renderer lock resolution": nested_string(
                renderer_lock,
                "renderer/package-lock.json",
                "packages",
                "node_modules/@mermaid-js/mermaid-cli",
                "version",
            ),
        },
    )
    puppeteer = matching_versions(
        "Puppeteer",
        {
            "renderer/package.json": exact_version(
                nested_string(renderer_package, "renderer/package.json", "dependencies", "puppeteer"),
                "renderer/package.json Puppeteer",
            ),
            "renderer lock root": nested_string(
                renderer_lock,
                "renderer/package-lock.json",
                "packages",
                "",
                "dependencies",
                "puppeteer",
            ),
            "renderer lock resolution": nested_string(
                renderer_lock,
                "renderer/package-lock.json",
                "packages",
                "node_modules/puppeteer",
                "version",
            ),
        },
    )
    frontend_mermaid = matching_versions(
        "Frontend Mermaid",
        {
            "frontend/package.json": exact_version(
                nested_string(frontend_package, "frontend/package.json", "dependencies", "mermaid"),
                "frontend/package.json Mermaid",
            ),
            "frontend lock root": nested_string(
                frontend_lock,
                "frontend/package-lock.json",
                "packages",
                "",
                "dependencies",
                "mermaid",
            ),
            "frontend lock resolution": nested_string(
                frontend_lock,
                "frontend/package-lock.json",
                "packages",
                "node_modules/mermaid",
                "version",
            ),
        },
    )
    renderer_mermaid = nested_string(
        renderer_lock,
        "renderer/package-lock.json",
        "packages",
        "node_modules/mermaid",
        "version",
    )
    if renderer_mermaid != frontend_mermaid:
        raise ContractError(
            "Preview and export Mermaid versions must match: "
            f"frontend={frontend_mermaid}, renderer={renderer_mermaid}"
        )

    dockerfile_path = root / "renderer/Dockerfile"
    try:
        dockerfile = dockerfile_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"{dockerfile_path}: could not read Dockerfile: {exc}") from exc
    if not PINNED_NODE_IMAGE.search(dockerfile):
        raise ContractError("renderer/Dockerfile must pin the Node base image by sha256 digest")
    chromium_match = CHROMIUM_SERIES.search(dockerfile)
    if chromium_match is None:
        raise ContractError("renderer/Dockerfile must declare a numeric CHROMIUM_SERIES")
    for required in (
        '"Chromium ${CHROMIUM_SERIES}."*',
        "> /chromium-version",
        "PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser",
    ):
        if required not in dockerfile:
            raise ContractError(f"renderer/Dockerfile is missing Chromium runtime assertion {required!r}")

    validate_dependabot(root / ".github/dependabot.yml")

    checksums = {relative: sha256(root / relative) for relative in CONTRACT_FILES}
    return {
        "schema_version": SCHEMA_VERSION,
        "versions": {
            "chromium_series": int(chromium_match.group(1)),
            "frontend_mermaid": frontend_mermaid,
            "mermaid_cli": cli,
            "renderer_mermaid": renderer_mermaid,
            "puppeteer": puppeteer,
        },
        "contract_file_sha256": checksums,
        "required_gates": list(REQUIRED_GATES),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        contract = build_contract(args.root.resolve())
    except ContractError as exc:
        parser.error(str(exc))

    rendered = json.dumps(contract, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(
        "Renderer dependency contract passed: "
        f"Mermaid {contract['versions']['frontend_mermaid']}, "
        f"CLI {contract['versions']['mermaid_cli']}, "
        f"Puppeteer {contract['versions']['puppeteer']}, "
        f"Chromium {contract['versions']['chromium_series']}.x."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
