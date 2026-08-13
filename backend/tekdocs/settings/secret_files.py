from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

MAX_SECRET_BYTES = 4096
DEFAULT_SECRET_ROOT = Path("/run/secrets")


def require_file_sources(names: tuple[str, ...], *, environment: Mapping[str, str] | None = None) -> None:
    """Reject direct or missing secret sources in the supported production profile."""

    values = os.environ if environment is None else environment
    for name in names:
        if values.get(name):
            raise _configuration_error(name, "direct values are not supported in the production profile")
        if not values.get(f"{name}_FILE"):
            raise _configuration_error(name, "a secret file is required in the production profile")


def _configuration_error(name: str, reason: str) -> ImproperlyConfigured:
    return ImproperlyConfigured(f"Invalid secret configuration for {name}: {reason}")


def read_secret(
    name: str,
    *,
    environment: Mapping[str, str] | None = None,
    default: str = "",
    secret_root: Path | None = None,
) -> str:
    """Resolve one sensitive setting without exposing its value or source path."""

    values = os.environ if environment is None else environment
    # Compose commonly materializes an optional environment key as an empty
    # string. Treat that as absent so a file source can supply the value.
    direct_present = bool(values.get(name, ""))
    file_name = f"{name}_FILE"
    file_present = file_name in values
    if direct_present and file_present:
        raise _configuration_error(name, f"set either {name} or {file_name}, not both")
    if direct_present:
        return values[name]
    if not file_present:
        return default

    configured_path = values[file_name]
    if not configured_path or "\x00" in configured_path:
        raise _configuration_error(name, f"{file_name} must identify a file")
    path = Path(configured_path)
    if not path.is_absolute():
        raise _configuration_error(name, f"{file_name} must be absolute")

    approved_root = (secret_root or Path(values.get("TEKDOCS_SECRET_ROOT", str(DEFAULT_SECRET_ROOT)))).resolve()
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(approved_root)
        descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except (FileNotFoundError, NotADirectoryError, OSError, RuntimeError, ValueError) as exc:
        raise _configuration_error(name, f"{file_name} is unavailable or outside the approved secret root") from exc

    with os.fdopen(descriptor, "rb") as source:
        details = os.fstat(source.fileno())
        if not stat.S_ISREG(details.st_mode):
            raise _configuration_error(name, f"{file_name} must identify a regular file")
        if details.st_uid not in {0, os.geteuid()}:
            raise _configuration_error(name, f"{file_name} has an unexpected owner")
        if details.st_mode & 0o033:
            raise _configuration_error(name, f"{file_name} cannot be writable or executable by group or other users")
        # Docker Compose secrets are mounted read-only and service-scoped at /run/secrets,
        # commonly with mode 0444. Elsewhere, group/other readability is rejected.
        if approved_root != DEFAULT_SECRET_ROOT and details.st_mode & 0o044:
            raise _configuration_error(name, f"{file_name} is readable by unintended users")
        raw = source.read(MAX_SECRET_BYTES + 1)
    if not raw or len(raw) > MAX_SECRET_BYTES:
        raise _configuration_error(name, f"{file_name} must contain 1-{MAX_SECRET_BYTES} bytes")
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _configuration_error(name, f"{file_name} must contain readable UTF-8") from exc
    if value.endswith("\n"):
        value = value[:-1]
        if value.endswith("\r"):
            value = value[:-1]
    if not value or value != value.strip() or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise _configuration_error(name, f"{file_name} must contain one non-empty printable value")
    return value
