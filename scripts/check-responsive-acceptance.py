#!/usr/bin/env python3
"""Validate the Phase 8 responsive workspace acceptance ledger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ACCEPTANCE = ROOT / "planning" / "responsive-layouts" / "acceptance.json"
ROUTES = ROOT / "planning" / "responsive-layouts" / "routes.json"

REQUIRED_WIDTHS = [320, 390, 768, 1024, 1280, 1440]
REQUIRED_ZOOM = [100, 200]
VALID_AUTOMATED_STATUSES = {"pending", "complete"}
VALID_HUMAN_STATUSES = {"pending", "complete"}
VALID_RECOVERY_STATUSES = {"pending", "backup_complete", "complete"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def string_value(value: Any, name: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{name} must be a non-empty string")
    return value.strip()


def repository_path(value: Any, name: str) -> Path:
    relative = string_value(value, name)
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, f"{name} must be repository-relative")
    resolved = ROOT / path
    require(resolved.is_file(), f"{name} does not exist: {relative}")
    return resolved


def string_list(value: Any, name: str) -> list[str]:
    require(isinstance(value, list) and bool(value), f"{name} must be a non-empty list")
    result = [string_value(item, f"{name}[{index}]") for index, item in enumerate(value)]
    require(len(result) == len(set(result)), f"{name} contains duplicates")
    return result


def validate_acceptance(
    acceptance_path: Path = ACCEPTANCE,
    routes_path: Path = ROUTES,
) -> tuple[int, int, int, int, int, int, int]:
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    routes = json.loads(routes_path.read_text(encoding="utf-8"))

    require(acceptance.get("widths") == REQUIRED_WIDTHS, "acceptance widths must retain the required matrix")
    require(acceptance.get("zoom_percent") == REQUIRED_ZOOM, "acceptance zoom levels must retain 100 and 200 percent")
    require(acceptance.get("short_height") == 600, "acceptance short height must remain 600 pixels")

    production_image = acceptance.get("production_image")
    require(isinstance(production_image, dict), "production_image must be an object")
    production_image_status = string_value(production_image.get("status"), "production_image.status")
    require(production_image_status in {"pending", "complete"}, "production_image has invalid status")
    repository_path(production_image.get("rehearsal"), "production_image.rehearsal")
    repository_path(production_image.get("record"), "production_image.record")

    release_gate = acceptance.get("release_gate")
    require(isinstance(release_gate, dict), "release_gate must be an object")
    release_gate_status = string_value(release_gate.get("status"), "release_gate.status")
    require(release_gate_status in {"pending", "complete"}, "release_gate has invalid status")
    require(string_value(release_gate.get("target"), "release_gate.target") == "release-gate", "release_gate.target must be release-gate")
    repository_path(release_gate.get("record"), "release_gate.record")

    workspaces = acceptance.get("workspace_acceptance")
    require(isinstance(workspaces, list) and bool(workspaces), "workspace_acceptance must be a non-empty list")
    in_progress_routes = {
        string_value(item.get("route"), "route")
        for item in routes
        if item.get("status") == "in_progress"
    }

    ids: set[str] = set()
    covered_routes: set[str] = set()
    automated_complete = 0
    backup_complete = 0
    recovery_complete = 0
    human_complete = 0
    for index, workspace in enumerate(workspaces):
        require(isinstance(workspace, dict), f"workspace_acceptance[{index}] must be an object")
        identifier = string_value(workspace.get("id"), f"workspace_acceptance[{index}].id")
        require(identifier not in ids, f"duplicate workspace acceptance id: {identifier}")
        ids.add(identifier)

        workspace_routes = string_list(workspace.get("routes"), f"{identifier}.routes")
        overlap = covered_routes.intersection(workspace_routes)
        require(not overlap, f"workspace routes are covered more than once: {', '.join(sorted(overlap))}")
        covered_routes.update(workspace_routes)

        automated_status = string_value(workspace.get("automated_status"), f"{identifier}.automated_status")
        require(automated_status in VALID_AUTOMATED_STATUSES, f"{identifier} has invalid automated_status")
        evidence = string_list(workspace.get("automated_evidence"), f"{identifier}.automated_evidence")
        for evidence_index, value in enumerate(evidence):
            repository_path(value, f"{identifier}.automated_evidence[{evidence_index}]")
        repository_path(workspace.get("live_runtime_evidence"), f"{identifier}.live_runtime_evidence")
        repository_path(workspace.get("production_route_evidence"), f"{identifier}.production_route_evidence")
        rehearsals = string_list(workspace.get("recovery_rehearsals"), f"{identifier}.recovery_rehearsals")
        for rehearsal_index, value in enumerate(rehearsals):
            repository_path(value, f"{identifier}.recovery_rehearsals[{rehearsal_index}]")
        recovery_status = string_value(workspace.get("recovery_status"), f"{identifier}.recovery_status")
        require(recovery_status in VALID_RECOVERY_STATUSES, f"{identifier} has invalid recovery status")
        repository_path(workspace.get("recovery_evidence"), f"{identifier}.recovery_evidence")
        if recovery_status in {"backup_complete", "complete"}:
            backup_complete += 1
        if recovery_status == "complete":
            recovery_complete += 1
        if automated_status == "complete":
            automated_complete += 1

        human_review = workspace.get("human_review")
        require(isinstance(human_review, dict), f"{identifier}.human_review must be an object")
        human_status = string_value(human_review.get("status"), f"{identifier}.human_review.status")
        require(human_status in VALID_HUMAN_STATUSES, f"{identifier} has invalid human review status")
        repository_path(human_review.get("record"), f"{identifier}.human_review.record")
        if human_status == "complete":
            string_value(human_review.get("reviewed_by"), f"{identifier}.human_review.reviewed_by")
            string_value(human_review.get("reviewed_at"), f"{identifier}.human_review.reviewed_at")
            human_complete += 1

    missing = sorted(in_progress_routes - covered_routes)
    stale = sorted(covered_routes - in_progress_routes)
    require(not missing, f"in-progress routes are missing workspace acceptance: {', '.join(missing)}")
    require(not stale, f"workspace acceptance contains routes that are not in progress: {', '.join(stale)}")
    return (
        len(workspaces),
        automated_complete,
        backup_complete,
        recovery_complete,
        int(production_image_status == "complete"),
        int(release_gate_status == "complete"),
        human_complete,
    )


def main() -> None:
    workspaces, automated_complete, backup_complete, recovery_complete, production_complete, release_complete, human_complete = (
        validate_acceptance()
    )
    print(
        "Responsive acceptance ledger passed: "
        f"{workspaces} workspace groups, {automated_complete} automated complete, "
        f"{backup_complete} backup rehearsed, "
        f"{recovery_complete} upgrade rehearsed, "
        f"{production_complete} production image rehearsed, "
        f"{release_complete} release gate complete, "
        f"{human_complete} human reviewed."
    )


if __name__ == "__main__":
    main()
