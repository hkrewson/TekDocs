"""Bounded completion protocol shared by the publication controller and server."""

from __future__ import annotations

import json
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

SOURCE_ROOT = Path(__file__).resolve().parents[3]
FAILURE_PHASES = {"setup", "call", "teardown"}
FAILURE_CATEGORIES = {"assertion", "database", "timeout", "exception"}


def safe_failure_report(error: BaseException, phase: str) -> dict[str, Any]:
    """Keep code locations, never messages, arguments, locals or request values."""
    category = "exception"
    if isinstance(error, AssertionError):
        category = "assertion"
    elif type(error).__module__.startswith(("django.db", "psycopg")):
        category = "database"
    elif isinstance(error, TimeoutError):
        category = "timeout"
    locations = []
    for frame in traceback.extract_tb(error.__traceback__):
        try:
            relative = Path(frame.filename).resolve().relative_to(SOURCE_ROOT)
        except ValueError:
            continue
        if (relative.parts[0] not in {"apps", "tekdocs"} and relative.as_posix() != "conftest.py"
            or relative.suffix != ".py"):
            continue
        locations.append({"file": relative.as_posix(), "line": frame.lineno})
    return {"version": 1, "phase": phase, "category": category, "locations": locations[-12:]}


def validate_failure_report(report: Any) -> dict[str, Any]:
    if (not isinstance(report, dict) or set(report) != {"version", "phase", "category", "locations"}
        or type(report["version"]) is not int or report["version"] != 1
        or report["phase"] not in FAILURE_PHASES or report["category"] not in FAILURE_CATEGORIES
        or not isinstance(report["locations"], list) or len(report["locations"]) > 12):
        raise ValueError("Invalid safe server failure report")
    for location in report["locations"]:
        if not isinstance(location, dict) or set(location) != {"file", "line"} or not isinstance(location["file"], str):
            raise ValueError("Invalid safe server failure report")
        selected = Path(location["file"])
        target = (SOURCE_ROOT / selected).resolve()
        if (selected.is_absolute() or ".." in selected.parts or selected.suffix != ".py"
            or not selected.parts or (selected.parts[0] not in {"apps", "tekdocs"} and str(selected) != "conftest.py")
            or not target.is_relative_to(SOURCE_ROOT) or not target.is_file()
            or type(location["line"]) is not int or not 1 <= location["line"] <= len(target.read_text().splitlines())):
            raise ValueError("Invalid safe server failure report")
    return report


def _budget(path: Path) -> dict[str, int]:
    budget = json.loads(path.read_text())
    fields = ("test_timeout_ms", "startup_timeout_ms", "suite_timeout_ms", "controller_grace_ms")
    if not isinstance(budget, dict) or any(
        type(budget.get(field)) is not int or budget[field] <= 0 for field in fields
    ):
        raise ValueError("Invalid publication browser budget")
    if not budget["test_timeout_ms"] < budget["suite_timeout_ms"] <= 900_000:
        raise ValueError("Invalid publication browser budget")
    if not budget["test_timeout_ms"] < budget["startup_timeout_ms"] <= budget["suite_timeout_ms"]:
        raise ValueError("Invalid publication browser budget")
    if budget["controller_grace_ms"] > 60_000:
        raise ValueError("Invalid publication browser budget")
    return budget


def startup_timeout_seconds(path: Path) -> float:
    """Bound fixture construction without using a controller-only deadline."""
    return _budget(path)["startup_timeout_ms"] / 1000


def completion_timeout_seconds(path: Path) -> float:
    """Allow the whole finite browser suite plus controller result handoff."""
    budget = _budget(path)
    return (budget["suite_timeout_ms"] + budget["controller_grace_ms"]) / 1000


def wait_for_browser_completion(
    path: Path,
    timeout_seconds: float,
    *,
    clock: Callable[[], float] = time.monotonic,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, str]:
    """Wait for the atomic browser result; never turn a failed result into success."""
    deadline = clock() + timeout_seconds
    while clock() < deadline:
        if path.exists():
            return json.loads(path.read_text())  # type: ignore[no-any-return]
        pause(0.1)
    raise AssertionError("The browser did not complete its acceptance phase")


if __name__ == "__main__":
    import sys

    try:
        checked = validate_failure_report(json.loads(Path(sys.argv[1]).read_text()))
    except (OSError, ValueError, TypeError, IndexError):
        print("Safe publication server failure locations are unavailable.")
        raise SystemExit(1) from None
    print("Publication server failure: " + json.dumps(checked, sort_keys=True))
