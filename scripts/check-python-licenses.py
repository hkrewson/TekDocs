from __future__ import annotations

import importlib.metadata
import re

DENIED = re.compile(r"AGPL-1|SSPL|BUSL|Commons Clause|proprietary", re.IGNORECASE)
REVIEWED_UNDECLARED = {
    "arrow",
    "isoduration",
    "markdown-it-py",
    "mdit-py-plugins",
    "mdurl",
    "prompt_toolkit",
    "sqlparse",
}

failures: list[str] = []
for distribution in importlib.metadata.distributions():
    name = distribution.metadata.get("Name", "unknown").lower()
    license_value = distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or ""
    if DENIED.search(license_value):
        failures.append(f"{name}: prohibited license declaration")
    if not license_value and name not in REVIEWED_UNDECLARED:
        failures.append(f"{name}: missing reviewed license declaration")

if failures:
    raise SystemExit("\n".join(sorted(set(failures))))
print("Python production dependency license policy passed.")
