"""Failure-only code locations; the original pytest outcome stays authoritative."""

import json
import os
from pathlib import Path

import pytest

from .publication_acceptance_protocol import safe_failure_report, validate_failure_report


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    directory = os.environ.get("TEKDOCS_PUBLICATION_ACCEPTANCE_DIRECTORY")
    if not directory or not report.failed or call.excinfo is None:
        return
    try:
        payload = validate_failure_report(safe_failure_report(call.excinfo.value, call.when))
        temporary = Path(directory) / "server-failure.partial"
        temporary.write_text(json.dumps(payload))
        temporary.chmod(0o644)
        temporary.replace(Path(directory) / "server-failure.json")
    except (OSError, ValueError):
        # Diagnostics cannot replace the original failure or retain raw values.
        return
