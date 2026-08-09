from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum

from django.db import connection, transaction

from .scoping import DataScope


class OrganizationRLSMode(StrEnum):
    MSP_ONLY = "msp"
    ORGANIZATION = "organization"
    ALL_AUTHORIZED = "all"


def bind_local_rls_scope(scope: DataScope, *, organization_mode: OrganizationRLSMode) -> None:
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

    organization_id = "" if scope.organization_id is None else str(scope.organization_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('tekdocs.tenant_id', %s, true)", [str(scope.tenant_id)])
        cursor.execute("SELECT set_config('tekdocs.organization_id', %s, true)", [organization_id])
        cursor.execute("SELECT set_config('tekdocs.organization_mode', %s, true)", [organization_mode.value])


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
    """Open a transaction and bind a fail-closed scope for jobs or commands."""

    with transaction.atomic():
        bind_local_rls_scope(scope, organization_mode=organization_mode)
        yield
