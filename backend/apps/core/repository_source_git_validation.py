"""Compare a validated source snapshot with one local managed Git repository."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import cast
from uuid import UUID

from .models import WorkspaceRepository
from .repository_service import (
    MAX_PINNED_SNAPSHOT_BYTES,
    RepositoryServiceError,
    pin_accepted_repository_for_publication,
    read_accepted_repository_markdown_files,
    read_repository_markdown_files_at_commit,
)
from .repository_source_exports import MAX_SOURCE_FILES
from .repository_source_validation import RepositorySourceValidationError


def verify_repository_source_against_git(manifest: dict[str, object], *, repository_id: UUID) -> None:
    """Require exact current files and every listed historical file at their Git objects.

    The caller must first validate the ZIP with verify_repository_source_snapshot.
    This checks the selected local repository, not an independent Git signature.
    """

    try:
        selected = WorkspaceRepository.objects.get(pk=repository_id)
        if str(selected.workspace_id) != manifest["workspace_id"]:
            raise RepositorySourceValidationError("The source snapshot belongs to a different Workspace.")
        with pin_accepted_repository_for_publication(repository_id) as repository:
            accepted, current = read_accepted_repository_markdown_files(
                repository_id=repository_id,
                max_files=MAX_SOURCE_FILES,
                max_bytes=MAX_PINNED_SNAPSHOT_BYTES,
                record_reconciliation=False,
            )
            if accepted.id != repository.accepted_commit_id or (
                accepted.object_id != manifest["accepted_commit"]
                or accepted.object_format != manifest["object_format"]
            ):
                raise RepositorySourceValidationError("The source snapshot does not match the accepted Git revision.")
            current_descriptors = cast(list[dict[str, str]], manifest["files"])
            expected_current = {
                item["path"].removeprefix("repository/"): item["sha256"] for item in current_descriptors
            }
            actual_current = {path: hashlib.sha256(source).hexdigest() for path, source in current}
            if actual_current != expected_current:
                raise RepositorySourceValidationError("The source snapshot current files differ from Git.")

            historical: dict[str, dict[str, str]] = defaultdict(dict)
            historical_descriptors = cast(list[dict[str, str]], manifest["historical_files"])
            for item in historical_descriptors:
                historical[item["commit"]][item["source_path"]] = item["sha256"]
            for object_id, expected_files in historical.items():
                commit, files = read_repository_markdown_files_at_commit(
                    repository_id=repository_id, object_id=object_id, record_reconciliation=False
                )
                if commit.object_id != object_id or commit.object_format != manifest["object_format"]:
                    raise RepositorySourceValidationError("A historical source Git revision differs.")
                actual_files = {path: hashlib.sha256(source).hexdigest() for path, source in files}
                if any(actual_files.get(path) != digest for path, digest in expected_files.items()):
                    raise RepositorySourceValidationError("A historical source file differs from Git.")
    except WorkspaceRepository.DoesNotExist as exc:
        raise RepositorySourceValidationError("The selected managed repository does not exist.") from exc
    except RepositoryServiceError as exc:
        raise RepositorySourceValidationError("The selected managed Git history is unavailable or unready.") from exc
