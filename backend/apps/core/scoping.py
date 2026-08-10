from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar
from uuid import UUID

from django.db import models


class ScopeRequiredError(RuntimeError):
    """Raised when a tenant-owned query omits its required scope."""


@dataclass(frozen=True, slots=True)
class DataScope:
    tenant_id: UUID
    workspace_id: UUID
    organization_id: UUID | None = None

    @classmethod
    def tenant(cls, tenant: Any) -> DataScope:
        tenant_id = _model_uuid(tenant, "tenant")
        return cls(tenant_id=tenant_id, workspace_id=_workspace_uuid(tenant_id=tenant_id, organization_id=None))

    @classmethod
    def organization(cls, tenant: Any, organization: Any) -> DataScope:
        tenant_id = _model_uuid(tenant, "tenant")
        organization_tenant_id = getattr(organization, "tenant_id", tenant_id)
        if organization_tenant_id != tenant_id:
            raise ValueError("Organization scope must belong to the selected tenant.")
        return cls(
            tenant_id=tenant_id,
            workspace_id=_workspace_uuid(
                tenant_id=tenant_id,
                organization_id=_model_uuid(organization, "organization"),
            ),
            organization_id=_model_uuid(organization, "organization"),
        )

    @classmethod
    def owner(cls, tenant: Any, organization: Any | None) -> DataScope:
        if organization is None:
            return cls.tenant(tenant)
        return cls.organization(tenant, organization)


def _workspace_uuid(*, tenant_id: UUID, organization_id: UUID | None) -> UUID:
    # Import through Django's registry to keep the model/scoping dependency acyclic.
    from django.apps import apps

    workspace = apps.get_model("core", "Workspace").objects.get(
        tenant_id=tenant_id,
        organization_id=organization_id,
    )
    return _model_uuid(workspace, "workspace")


def _model_uuid(value: Any, label: str) -> UUID:
    candidate = getattr(value, "pk", value)
    if isinstance(candidate, UUID):
        return candidate
    try:
        return UUID(str(candidate))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"A valid {label} UUID is required.") from exc


ModelT = TypeVar("ModelT", bound=models.Model)


class TenantScopedQuerySet(models.QuerySet[ModelT]):
    def for_tenant(self, tenant: Any) -> TenantScopedQuerySet[ModelT]:
        tenant_id = _model_uuid(tenant, "tenant")
        return self.filter(tenant_id=tenant_id)

    def for_scope(self, scope: DataScope) -> TenantScopedQuerySet[ModelT]:
        return self.for_tenant(scope.tenant_id)


class OrganizationScopedQuerySet(TenantScopedQuerySet[ModelT]):
    def for_scope(self, scope: DataScope) -> OrganizationScopedQuerySet[ModelT]:
        queryset = self.filter(tenant_id=scope.tenant_id)
        if scope.organization_id is None:
            return queryset.filter(organization__isnull=True)
        return queryset.filter(organization_id=scope.organization_id)


class TenantScopedManager(models.Manager[ModelT]):
    queryset_class = TenantScopedQuerySet

    def get_queryset(self) -> TenantScopedQuerySet[ModelT]:
        raise ScopeRequiredError("Tenant-owned queries must call for_tenant() or for_scope().")

    def _unfiltered_queryset(self) -> TenantScopedQuerySet[ModelT]:
        return self.queryset_class(model=self.model, using=self._db, hints=self._hints)  # type: ignore[attr-defined]

    def for_tenant(self, tenant: Any) -> TenantScopedQuerySet[ModelT]:
        return self._unfiltered_queryset().for_tenant(tenant)

    def for_scope(self, scope: DataScope) -> TenantScopedQuerySet[ModelT]:
        return self._unfiltered_queryset().for_scope(scope)


class OrganizationScopedManager(TenantScopedManager[ModelT]):
    queryset_class = OrganizationScopedQuerySet

    def for_scope(self, scope: DataScope) -> OrganizationScopedQuerySet[ModelT]:
        queryset = self._unfiltered_queryset()
        if not isinstance(queryset, OrganizationScopedQuerySet):
            raise TypeError("Organization-scoped manager is misconfigured.")
        return queryset.for_scope(scope)
