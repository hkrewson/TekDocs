"""Bounded completion protocol shared by the publication controller and server."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path


def completion_timeout_seconds(path: Path) -> float:
    """Allow the whole finite browser suite plus controller result handoff."""
    budget = json.loads(path.read_text())
    fields = ("test_timeout_ms", "suite_timeout_ms", "controller_grace_ms")
    if not isinstance(budget, dict) or any(
        type(budget.get(field)) is not int or budget[field] <= 0 for field in fields
    ):
        raise ValueError("Invalid publication browser budget")
    if not budget["test_timeout_ms"] < budget["suite_timeout_ms"] <= 900_000:
        raise ValueError("Invalid publication browser budget")
    if budget["controller_grace_ms"] > 60_000:
        raise ValueError("Invalid publication browser budget")
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
