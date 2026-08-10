from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from .models import AuditEvent, CommercialContract, ContractCost, Entity, EntityVisibility, Organization, Tenant
from .scoping import DataScope


class CommercialError(Exception):
    pass


def _validate(record) -> None:  # type: ignore[no-untyped-def]
    try:
        record.full_clean()
    except ValidationError as exc:
        raise CommercialError(" ".join(exc.messages)) from exc


def contracts_for_scope(
    scope: DataScope, *, query: str = "", include_costs: bool = False
) -> QuerySet[CommercialContract]:
    records = (
        CommercialContract.scoped.for_scope(scope)
        .filter(archived_at__isnull=True, entity__archived_at__isnull=True)
        .select_related("entity", "provider__entity")
    )
    if include_costs:
        records = records.prefetch_related(
            Prefetch("costs", queryset=ContractCost.objects.filter(archived_at__isnull=True))
        )
    normalized = query.strip()[:100]
    if normalized:
        records = records.filter(
            Q(entity__display_name__icontains=normalized)
            | Q(provider__entity__display_name__icontains=normalized)
            | Q(reference__icontains=normalized)
            | Q(description__icontains=normalized)
        )
    return records


def _record_scope(tenant: Tenant, organization: Organization | None) -> DataScope:
    return DataScope.organization(tenant, organization) if organization is not None else DataScope.tenant(tenant)


def provider_choices(tenant: Tenant, *, query: str = "") -> QuerySet[Organization]:
    records = (
        Organization.objects.filter(
            tenant=tenant,
            entity__archived_at__isnull=True,
            classifications__kind__in=("vendor", "manufacturer", "partner"),
        )
        .select_related("entity")
        .distinct()
        .order_by("entity__display_name")
    )
    normalized = query.strip()[:100]
    return records.filter(entity__display_name__icontains=normalized) if normalized else records


def _provider(tenant: Tenant, provider_id: UUID) -> Organization:
    record = provider_choices(tenant).filter(entity_id=provider_id).first()
    if record is None:
        raise CommercialError("The selected provider is unavailable.")
    return record


@transaction.atomic
def create_contract(
    *, tenant: Tenant, organization: Organization | None, actor_id: UUID, values: dict[str, object]
) -> CommercialContract:
    provider_id = values.pop("provider_id")
    entity = Entity.objects.create(
        tenant=tenant,
        organization=organization,
        entity_type="commercial_contract",
        display_name=str(values.pop("name")).strip(),
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    record = CommercialContract(
        tenant=tenant,
        organization=organization,
        entity=entity,
        provider=_provider(tenant, provider_id),  # type: ignore[arg-type]
        created_by_id=actor_id,
        **values,
    )
    _validate(record)
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="commercial_contract.created", entity_id=entity.id, metadata={}
    )
    return contracts_for_scope(_record_scope(tenant, organization)).get(pk=record.pk)


@transaction.atomic
def update_contract(*, record: CommercialContract, actor_id: UUID, values: dict[str, object]) -> CommercialContract:
    locked = CommercialContract.objects.select_for_update().select_related("entity").get(pk=record.pk)
    if "name" in values:
        locked.entity.display_name = str(values.pop("name")).strip()
        locked.entity.full_clean()
        locked.entity.save(update_fields=("display_name", "updated_at"))
    if "provider_id" in values:
        locked.provider = _provider(locked.tenant, values.pop("provider_id"))  # type: ignore[arg-type]
    for key, value in values.items():
        setattr(locked, key, value)
    _validate(locked)
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="commercial_contract.updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return contracts_for_scope(_record_scope(locked.tenant, locked.organization)).get(pk=locked.pk)


@transaction.atomic
def archive_contract(*, record: CommercialContract, actor_id: UUID) -> None:
    locked = CommercialContract.objects.select_for_update().select_related("entity").get(pk=record.pk)
    archived_at = timezone.now()
    locked.costs.filter(archived_at__isnull=True).update(archived_at=archived_at, updated_at=archived_at)
    locked.archived_at = archived_at
    locked.save(update_fields=("archived_at", "updated_at"))
    locked.entity.archived_at = archived_at
    locked.entity.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="commercial_contract.archived",
        entity_id=locked.entity_id,
        metadata={},
    )


@transaction.atomic
def create_cost(*, contract: CommercialContract, actor_id: UUID, values: dict[str, object]) -> CommercialContract:
    locked = CommercialContract.objects.select_for_update().get(pk=contract.pk)
    values["currency"] = str(values["currency"]).upper()
    cost = ContractCost(tenant=locked.tenant, organization=locked.organization, contract=locked, **values)
    _validate(cost)
    cost.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="commercial_contract.cost_created",
        entity_id=locked.entity_id,
        metadata={"cost_id": str(cost.id)},
    )
    return contracts_for_scope(_record_scope(locked.tenant, locked.organization)).get(pk=locked.pk)


@transaction.atomic
def update_cost(
    *, contract: CommercialContract, cost_id: UUID, actor_id: UUID, values: dict[str, object]
) -> CommercialContract:
    locked = CommercialContract.objects.select_for_update().get(pk=contract.pk)
    cost = (
        ContractCost.objects.select_for_update()
        .filter(
            id=cost_id,
            tenant=locked.tenant,
            organization=locked.organization,
            contract=locked,
            archived_at__isnull=True,
        )
        .first()
    )
    if cost is None:
        raise CommercialError("The cost entry is unavailable.")
    if "currency" in values:
        values["currency"] = str(values["currency"]).upper()
    for key, value in values.items():
        setattr(cost, key, value)
    _validate(cost)
    cost.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="commercial_contract.cost_updated",
        entity_id=locked.entity_id,
        metadata={"cost_id": str(cost.id)},
    )
    return contracts_for_scope(_record_scope(locked.tenant, locked.organization)).get(pk=locked.pk)


@transaction.atomic
def archive_cost(*, contract: CommercialContract, cost_id: UUID, actor_id: UUID) -> CommercialContract:
    locked = CommercialContract.objects.select_for_update().get(pk=contract.pk)
    cost = (
        ContractCost.objects.select_for_update()
        .filter(
            id=cost_id,
            tenant=locked.tenant,
            organization=locked.organization,
            contract=locked,
            archived_at__isnull=True,
        )
        .first()
    )
    if cost is None:
        raise CommercialError("The cost entry is unavailable.")
    cost.archived_at = timezone.now()
    cost.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="commercial_contract.cost_archived",
        entity_id=locked.entity_id,
        metadata={"cost_id": str(cost.id)},
    )
    return contracts_for_scope(_record_scope(locked.tenant, locked.organization)).get(pk=locked.pk)
