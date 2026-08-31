#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend" / "apps" / "core" / "capabilities.py"
FRONTEND = ROOT / "frontend" / "src" / "product" / "capabilities.ts"
MATRIX = ROOT / "docs" / "PRODUCT_BOUNDARY.md"
EXCLUDED = {"tickets", "accounting"}


def registry_keys(source: str, marker: str, end_marker: str, pattern: str) -> set[str]:
    body = source.split(marker, 1)[1].split(end_marker, 1)[0]
    return set(re.findall(pattern, body, flags=re.MULTILINE))


def main() -> int:
    backend_keys = registry_keys(
        BACKEND.read_text(encoding="utf-8"),
        "CAPABILITY_REGISTRY: dict[str, CapabilityDefinition] = {",
        "}\n\nCAPABILITY_PERMISSIONS",
        r'^    "([a-z_]+)": CapabilityDefinition',
    )
    frontend_keys = registry_keys(
        FRONTEND.read_text(encoding="utf-8"),
        "export const capabilityRegistry = {",
        "} as const",
        r"^  ([a-z_]+): \{",
    )
    if backend_keys != frontend_keys:
        raise SystemExit(
            f"Capability registry drift: backend-only={sorted(backend_keys - frontend_keys)}, "
            f"frontend-only={sorted(frontend_keys - backend_keys)}"
        )
    if backend_keys & EXCLUDED:
        raise SystemExit(f"Excluded capabilities returned: {sorted(backend_keys & EXCLUDED)}")

    matrix = MATRIX.read_text(encoding="utf-8")
    rows = [line for line in matrix.splitlines() if line.startswith("|") and not line.startswith(("| ---", "| Capability"))]
    for row in rows:
        columns = [column.strip() for column in row.strip("|").split("|")]
        if len(columns) != 5 or columns[1] not in {"supported", "experimental", "excluded"} or columns[2] not in {"supported", "experimental", "excluded"}:
            raise SystemExit(f"Invalid capability matrix row: {row}")
        if ("experimental" in columns[1:3] or columns[1] != columns[2]) and "github.com/hkrewson/TekDocs/issues/" not in columns[4]:
            raise SystemExit(f"Experimental or deferred row lacks an issue: {columns[0]}")

    print(f"Product boundary passed: {len(backend_keys)} visible capabilities and {len(rows)} matrix rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
