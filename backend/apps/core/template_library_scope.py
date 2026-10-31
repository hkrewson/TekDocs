"""Temporary exact-Workspace scopes for an explicitly authorized template operation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from django.db import connection, transaction

from .document_migration_publications import publication_migration_actor_allowed
from .document_template_migration import TemplateMigrationError
from .models import Workspace
from .rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from .scoping import DataScope

_SCOPE_SETTINGS = (
    "tekdocs.tenant_id",
    "tekdocs.workspace_id",
    "tekdocs.organization_id",
    "tekdocs.organization_mode",
    "tekdocs.user_id",
    "tekdocs.principal_mode",
)


@contextmanager
def editable_template_workspace_scope(workspace: Workspace, actor_id: UUID) -> Iterator[None]:
    if not publication_migration_actor_allowed(workspace=workspace, actor_id=actor_id):
        raise TemplateMigrationError("template_migration_not_authorized")
    outer = connection.in_atomic_block
    previous: tuple[str, ...] = ()
    if outer:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT " + ", ".join("COALESCE(current_setting(%s, true), '')" for _name in _SCOPE_SETTINGS),
                list(_SCOPE_SETTINGS),
            )
            previous = cursor.fetchone()
    scope = (
        DataScope.organization(workspace.tenant, workspace.organization)
        if workspace.organization
        else DataScope.tenant(workspace.tenant)
    )
    try:
        with transaction.atomic():
            bind_local_rls_scope(
                scope,
                organization_mode=(
                    OrganizationRLSMode.ORGANIZATION if workspace.organization else OrganizationRLSMode.MSP_ONLY
                ),
                actor_user_id=actor_id,
                principal_mode=RLSPrincipalMode.USER,
            )
            yield
    finally:
        if outer and not connection.needs_rollback:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT " + ", ".join("set_config(%s, %s, true)" for _name in _SCOPE_SETTINGS),
                    [item for name, value in zip(_SCOPE_SETTINGS, previous, strict=True) for item in (name, value)],
                )
