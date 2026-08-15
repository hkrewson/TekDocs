from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from uuid import UUID

from django.db import connection, transaction

from .scoping import DataScope


class OrganizationRLSMode(StrEnum):
    MSP_ONLY = "msp"
    ORGANIZATION = "organization"
    ALL_AUTHORIZED = "all"


class RLSPrincipalMode(StrEnum):
    USER = "user"
    SYSTEM = "system"


_PRESERVE_ACTOR = object()


def bind_local_rls_scope(
    scope: DataScope,
    *,
    organization_mode: OrganizationRLSMode,
    actor_user_id: UUID | None | object = _PRESERVE_ACTOR,
    principal_mode: RLSPrincipalMode | None = None,
) -> None:
    """Bind PostgreSQL RLS inputs to the current transaction only.

    Policy activation is intentionally staged. Calling this helper outside an atomic
    transaction would allow a scope value to leak through a pooled connection, so it
    fails before touching the database.
    """

    if connection.vendor != "postgresql":
        raise RuntimeError("PostgreSQL is required for RLS scope binding.")
    if not connection.in_atomic_block:
        raise RuntimeError("RLS scope binding requires an atomic transaction.")
    if organization_mode == OrganizationRLSMode.ORGANIZATION and scope.organization_id is None:
        raise ValueError("Organization mode requires an organization-scoped DataScope.")
    if organization_mode != OrganizationRLSMode.ORGANIZATION and scope.organization_id is not None:
        raise ValueError("An organization-scoped DataScope requires organization mode.")
    if principal_mode == RLSPrincipalMode.USER and not isinstance(actor_user_id, UUID):
        raise ValueError("User principal mode requires an actor user ID.")
    if principal_mode == RLSPrincipalMode.SYSTEM and actor_user_id is not None:
        raise ValueError("System principal mode cannot carry a user actor.")

    organization_id = "" if scope.organization_id is None else str(scope.organization_id)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                set_config('tekdocs.tenant_id', %s, true),
                set_config('tekdocs.workspace_id', %s, true),
                set_config('tekdocs.organization_id', %s, true),
                set_config('tekdocs.organization_mode', %s, true)
            """,
            [
                str(scope.tenant_id),
                str(scope.workspace_id),
                organization_id,
                organization_mode.value,
            ],
        )
        if actor_user_id is not _PRESERVE_ACTOR:
            cursor.execute(
                "SELECT set_config('tekdocs.user_id', %s, true)",
                [str(actor_user_id) if isinstance(actor_user_id, UUID) else ""],
            )
        if principal_mode is not None:
            cursor.execute(
                "SELECT set_config('tekdocs.principal_mode', %s, true)",
                [principal_mode.value],
            )


def current_rls_tenant_id() -> str:
    if connection.vendor != "postgresql":
        return ""
    with connection.cursor() as cursor:
        cursor.execute("SELECT COALESCE(current_setting('tekdocs.tenant_id', true), '')")
        return str(cursor.fetchone()[0])


def bind_tenant_scope_if_postgresql(tenant: object) -> None:
    if connection.vendor == "postgresql":
        bind_local_rls_scope(DataScope.tenant(tenant), organization_mode=OrganizationRLSMode.MSP_ONLY)


@contextmanager
def rls_scope(scope: DataScope, *, organization_mode: OrganizationRLSMode) -> Iterator[None]:
    """Open a transaction and preserve an existing request principal."""

    with transaction.atomic():
        bind_local_rls_scope(scope, organization_mode=organization_mode)
        yield


@contextmanager
def system_rls_scope(scope: DataScope, *, organization_mode: OrganizationRLSMode) -> Iterator[None]:
    """Open a transaction for a trusted tenant-scoped worker or server operation."""

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "COALESCE(current_setting('tekdocs.user_id', true), ''), "
                "COALESCE(current_setting('tekdocs.principal_mode', true), '')"
            )
            previous_actor, previous_principal = cursor.fetchone()
        bind_local_rls_scope(
            scope,
            organization_mode=organization_mode,
            actor_user_id=None,
            principal_mode=RLSPrincipalMode.SYSTEM,
        )
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT "
                    "set_config('tekdocs.user_id', %s, true), "
                    "set_config('tekdocs.principal_mode', %s, true)",
                    [previous_actor, previous_principal],
                )


@contextmanager
def system_rls_scope_if_postgresql(
    scope: DataScope,
    *,
    organization_mode: OrganizationRLSMode,
) -> Iterator[None]:
    """Use a trusted system scope on PostgreSQL and remain portable in unit tests."""

    if connection.vendor != "postgresql":
        yield
        return
    with system_rls_scope(scope, organization_mode=organization_mode):
        yield
