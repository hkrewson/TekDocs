"""Temporary exact-Workspace scope after centralized edit authorization."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from django.db import connection, transaction
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.accounts.policy import PermissionKey, context_has_permission, require_installation_member

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
def editable_workspace_scope(workspace: Workspace, actor_id: UUID) -> Iterator[None]:
    # This binds an already selected operation's scope; protected callers keep
    # their own MFA gate. Ordinary handoff service semantics remain unchanged.
    actor = User.objects.filter(pk=actor_id, is_active=True).first()
    if actor is None:
        raise PermissionDenied("Workspace is unavailable for this operation.")
    member = require_installation_member(actor)
    if member.tenant.id != workspace.tenant_id or not context_has_permission(
        member, PermissionKey.DOCUMENTS_EDIT, organization=workspace.organization,
    ):
        raise PermissionDenied("Workspace is unavailable for this operation.")
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
