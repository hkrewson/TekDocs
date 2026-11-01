#!/usr/bin/env python3
"""Value-minimized, read-only evidence for a failed synthetic workspace rehearsal."""

import json
import re
import sys

INPUT_LIMIT = 64 * 1024
SERVICES = {"worker", "scheduler", "valkey"}


def recent_task_signals(source: bytes) -> dict:
    rows = source[:INPUT_LIMIT].decode("utf-8", errors="replace").splitlines()
    outbox = [row for row in rows if "Task apps.core.tasks.dispatch_outbox_events[" in row]
    return {
        "input_truncated": len(source) > INPUT_LIMIT,
        "outbox_received": sum(" received" in row for row in outbox),
        "outbox_succeeded": sum(" succeeded in " in row for row in outbox),
        "outbox_failed": sum(" raised unexpected:" in row for row in outbox),
        "outbox_scheduled": sum("Sending due task dispatch-transactional-outbox " in row for row in rows),
        "worker_errors": sum(bool(re.search(r"worker-\d+\s*\|.*\bERROR\b", row)) for row in rows),
        "scheduler_errors": sum(bool(re.search(r"scheduler-\d+\s*\|.*\bERROR\b", row)) for row in rows),
    }


def service_state(source: bytes) -> dict:
    state = json.loads(source)
    if not isinstance(state, dict):
        raise ValueError
    if any(type(state.get(field)) is not bool for field in ("running", "restarting", "oom_killed")):
        raise ValueError
    code = state.get("exit_code")
    if type(code) is not int or not 0 <= code <= 255:
        raise ValueError
    return {field: state[field] for field in ("running", "restarting", "oom_killed", "exit_code")}


def main() -> int:
    args = sys.argv[1:]
    report = {"schema_version": 1}
    try:
        if args == ["logs"]:
            report.update(recent_task_signals(sys.stdin.buffer.read(INPUT_LIMIT + 1)))
        elif len(args) == 2 and args[0] == "service" and args[1] in SERVICES:
            report["service"] = args[1]
            report.update(service_state(sys.stdin.buffer.read(INPUT_LIMIT + 1)))
        else:
            print("Expected logs or service with a supported service name.", file=sys.stderr)
            return 2
    except Exception:
        report["state"] = "unavailable"
        print(json.dumps(report, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
