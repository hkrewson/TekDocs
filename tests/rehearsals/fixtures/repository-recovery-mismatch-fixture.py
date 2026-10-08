"""Inject and clear one Git/DB accepted-head mismatch in the isolated recovery fixture."""

import os

from apps.core.models import WorkspaceRepository
from apps.core.repository_recovery import RepositoryRecoveryError, _git
from apps.core.repository_service import CANONICAL_REF
from apps.core.repository_storage import resolve_managed_repository_path


def fixture_repository():
    for repository in WorkspaceRepository.objects.select_related("tenant", "accepted_commit").order_by("id"):
        if repository.tenant.name != "Validation Recovery MSP" or repository.accepted_commit is None:
            continue
        _, path = resolve_managed_repository_path(repository)
        accepted = repository.accepted_commit.object_id
        try:
            parent = _git("rev-parse", f"{accepted}^", git_dir=path).decode().strip()
        except RepositoryRecoveryError:
            continue
        return path, accepted, parent
    raise RuntimeError("The isolated recovery fixture has no repository with a prior commit.")


path, accepted, parent = fixture_repository()
mode = os.environ.get("TEKDOCS_RECOVERY_FAULT_MODE")
if mode == "break":
    assert _git("rev-parse", CANONICAL_REF, git_dir=path).decode().strip() == accepted
    _git("update-ref", CANONICAL_REF, parent, accepted, git_dir=path)
elif mode == "repair":
    assert _git("rev-parse", CANONICAL_REF, git_dir=path).decode().strip() == parent
    _git("update-ref", CANONICAL_REF, accepted, parent, git_dir=path)
elif mode == "verify":
    assert _git("rev-parse", CANONICAL_REF, git_dir=path).decode().strip() == accepted
else:
    raise RuntimeError("TEKDOCS_RECOVERY_FAULT_MODE must be break, repair, or verify.")
