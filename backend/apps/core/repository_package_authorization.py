"""Internal final authorization of a repository package, without delivery."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, require_permission

from .models import AuditEvent, RepositoryPackageAuthorization, RepositoryPublicationPackage
from .repository_publication_packages import verify_repository_publication_package


class RepositoryPackageAuthorizationError(RuntimeError):
    """The exact package cannot receive a final staff decision."""


@transaction.atomic
def decide_repository_package(
    *, package_id: UUID, outcome: str, reason: str, actor: User,
) -> RepositoryPackageAuthorization:
    package = RepositoryPublicationPackage.objects.select_for_update(of=("self",)).get(pk=package_id)
    member = require_permission(actor, PermissionKey.DOCUMENTS_APPROVE, organization=package.organization)
    if member.tenant.id != package.tenant_id:
        raise RepositoryPackageAuthorizationError("Package scope does not match actor")
    if RepositoryPackageAuthorization.objects.filter(package=package).exists():
        raise RepositoryPackageAuthorizationError("Package already has a final authorization decision")
    if outcome not in RepositoryPackageAuthorization.Outcome.values or not reason.strip():
        raise RepositoryPackageAuthorizationError("Outcome and reason are required")
    if (
        outcome == RepositoryPackageAuthorization.Outcome.AUTHORIZED_FOR_PUBLICATION
        and package.created_by_id == actor.id
    ):
        raise RepositoryPackageAuthorizationError("Package creator cannot authorize their own package")
    if not verify_repository_publication_package(package):
        raise RepositoryPackageAuthorizationError("Retained publication package failed verification")
    authorization = RepositoryPackageAuthorization.objects.create(
        tenant_id=package.tenant_id,
        organization_id=package.organization_id,
        workspace_id=package.workspace_id,
        package=package,
        outcome=outcome,
        reason=reason.strip(),
        actor=actor,
    )
    AuditEvent.objects.create(
        tenant_id=package.tenant_id,
        actor=actor,
        action="repository.package_authorization.recorded",
        entity_id=authorization.id,
        metadata={"package_id": str(package.id), "outcome": outcome},
    )
    return authorization
