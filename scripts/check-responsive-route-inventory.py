#!/usr/bin/env python3
"""Verify that the responsive-layout route inventory matches the application router."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "frontend" / "src" / "App.tsx"
CAPABILITIES = ROOT / "frontend" / "src" / "product" / "capabilities.ts"
INVENTORY = ROOT / "planning" / "responsive-layouts" / "routes.json"

VALID_STATUSES = {"pending", "in_progress", "complete"}
DEFAULT_STATES = "All applicable states in acceptance.json; applicability must be recorded during migration."
ORGANIZATION_PREFIX = "/workspaces/organizations/:organizationId"
SUPPORTED_SURFACE_ROUTES = {"/auth/reset-password", "/portal"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def string_value(value: Any, name: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{name} must be a non-empty string")
    return value.strip()


def capability_routes(source: str) -> set[str]:
    body = source.split("export const capabilityRegistry = {", 1)[1].split("} as const", 1)[0]
    routes: set[str] = set()
    pattern = re.compile(
        r"^\s*(?P<id>[a-z_]+):\s*\{[^\n]*path:\s*'(?P<path>/[^']+)'[^\n]*scopes:\s*\[(?P<scopes>[^]]+)]",
        re.MULTILINE,
    )
    for match in pattern.finditer(body):
        if "'organization'" not in match.group("scopes"):
            continue
        identifier = match.group("id")
        if identifier != "overview":
            routes.add(f"{ORGANIZATION_PREFIX}/{identifier}")
    return routes


def application_routes(app_source: str, capability_source: str) -> set[str]:
    routes: set[str] = set()
    for tag in re.findall(r"<Route\b[^>]*>", app_source):
        path = re.search(r'\bpath="([^"]+)"', tag)
        if path:
            routes.add(path.group(1))
    routes.update(capability_routes(capability_source))
    routes.update(SUPPORTED_SURFACE_ROUTES)
    return routes


def evidence_path(value: str) -> Path:
    path = Path(value)
    if value.startswith(("frontend/", "backend/", "planning/", "scripts/", "tests/")):
        return ROOT / path
    return INVENTORY.parent / path


def validate_inventory(
    inventory_path: Path = INVENTORY,
    app_path: Path = APP,
    capabilities_path: Path = CAPABILITIES,
) -> tuple[int, int, int]:
    raw = json.loads(inventory_path.read_text(encoding="utf-8"))
    require(isinstance(raw, list) and bool(raw), "responsive route inventory must be a non-empty list")

    routes: set[str] = set()
    complete = 0
    in_progress = 0
    for index, item in enumerate(raw):
        require(isinstance(item, dict), f"route entry {index} must be an object")
        route = string_value(item.get("route"), f"route entry {index}.route")
        require(route not in routes, f"duplicate responsive route: {route}")
        routes.add(route)

        source = string_value(item.get("source"), f"{route}.source")
        require((ROOT / source).is_file(), f"{route} source does not exist: {source}")
        status = string_value(item.get("status"), f"{route}.status")
        require(status in VALID_STATUSES, f"{route} has invalid status: {status}")
        states = string_value(item.get("states"), f"{route}.states")
        evidence = item.get("evidence")
        require(isinstance(evidence, list), f"{route}.evidence must be a list")

        if status != "pending":
            require(states != DEFAULT_STATES, f"{route} must replace the default state inventory")
            require(bool(evidence), f"{route} must record evidence before leaving pending")
            for evidence_index, value in enumerate(evidence):
                evidence_value = string_value(value, f"{route}.evidence[{evidence_index}]")
                require(evidence_path(evidence_value).exists(), f"{route} evidence does not exist: {evidence_value}")
        if status == "complete":
            complete += 1
        elif status == "in_progress":
            in_progress += 1

    expected = application_routes(
        app_path.read_text(encoding="utf-8"),
        capabilities_path.read_text(encoding="utf-8"),
    )
    missing = sorted(expected - routes)
    extra = sorted(routes - expected)
    require(not missing, f"responsive route inventory is missing routes: {', '.join(missing)}")
    require(not extra, f"responsive route inventory contains stale routes: {', '.join(extra)}")
    return len(routes), complete, in_progress


def main() -> None:
    routes, complete, in_progress = validate_inventory()
    print(
        "Responsive route inventory passed: "
        f"{routes} routes, {complete} complete, {in_progress} in progress, "
        f"{routes - complete - in_progress} pending."
    )


if __name__ == "__main__":
    main()
