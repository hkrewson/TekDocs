"""Validate decrypted recovery archive structure before restore."""

from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path, PurePosixPath

from .settings.secret_files import MAX_SECRET_BYTES

REQUIRED_SECRETS = frozenset({
    "django_secret_key", "postgres_owner_password", "postgres_runtime_password",
    "tekdocs_master_key", "publication_signing_key",
})
OPTIONAL_SECRETS = frozenset({"bootstrap_token", "email_host_password", "oidc_client_secret"})


def validate_media_archive(path: Path) -> None:
    """Read regular media bytes without extracting or trusting archive paths."""
    seen: set[str] = set()
    files: set[str] = set()
    parents: set[str] = set()
    try:
        with tarfile.open(path, "r:") as archive:
            for member in archive:
                name = member.name
                if name.startswith("./"):
                    name = name[2:]
                parts = name.split("/")
                if (
                    (name != "." and any(part in {"", ".", ".."} for part in parts))
                    or "\\" in name
                    or name in seen
                    or not (member.isfile() or member.isdir())
                    or member.issparse()
                    or member.size < 0
                    or (member.isdir() and member.size != 0)
                    or (name == "." and not member.isdir())
                ):
                    raise ValueError("The recovery media archive contains an invalid member.")
                ancestors = {str(parent) for parent in PurePosixPath(name).parents} - {"."}
                if ancestors & files or (member.isfile() and name in parents):
                    raise ValueError("The recovery media archive contains conflicting paths.")
                seen.add(name)
                parents.update(ancestors)
                if member.isfile():
                    files.add(name)
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ValueError("The recovery media archive is unreadable.")
                    remaining = member.size
                    with stream:
                        while remaining:
                            chunk = stream.read(min(remaining, 65536))
                            if not chunk:
                                raise ValueError("The recovery media archive is truncated.")
                            remaining -= len(chunk)
    except (OSError, tarfile.TarError) as exc:
        raise ValueError("The recovery media archive is unavailable or invalid.") from exc


def validate_secret_archive(path: Path) -> None:
    seen: set[str] = set()
    try:
        with tarfile.open(path, "r:") as archive:
            for member in archive:
                if (
                    member.name not in REQUIRED_SECRETS | OPTIONAL_SECRETS
                    or member.name in seen
                    or not member.isfile()
                    or member.issparse()
                    or not 1 <= member.size <= MAX_SECRET_BYTES
                ):
                    raise ValueError("The recovery secret archive contains an invalid member.")
                seen.add(member.name)
                stream = archive.extractfile(member)
                if stream is None or len(stream.read(MAX_SECRET_BYTES + 1)) != member.size:
                    raise ValueError("The recovery secret archive is truncated.")
    except (OSError, tarfile.TarError) as exc:
        raise ValueError("The recovery secret archive is unavailable or invalid.") from exc
    if not REQUIRED_SECRETS <= seen:
        raise ValueError("The recovery secret archive is incomplete.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--kind", choices=("secrets", "media"), default="secrets")
    arguments = parser.parse_args()
    try:
        if arguments.kind == "media":
            validate_media_archive(arguments.archive)
        else:
            validate_secret_archive(arguments.archive)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
