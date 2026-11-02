"""Named custody and authorization evidence for one approved foreign fragment."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class LibrarySourceDescriptor:
    repository_id: UUID
    storage_relative_path: str
    accepted_commit: str
    object_format: str
    body_sha256: str
    scope_sha256: str
    revision_id: UUID
    retention_manifest_sha256: str | None = None
