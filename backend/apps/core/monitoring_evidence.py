from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_evidence_digest(kind: str, values: dict[str, Any]) -> str:
    payload = {"schema": 1, "kind": kind, **values}
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()

