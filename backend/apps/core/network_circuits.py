from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Prefetch, QuerySet

from .commercial import contracts_for_scope, provider_choices
from .models import (
    AuditEvent,
    CommercialContract,
    Entity,
    EntityVisibility,
    Location,
    NetworkCircuit,
    NetworkCircuitHandoff,
    NetworkDevice,
    NetworkInterface,
    Organization,
    Site,
    Tenant,
    workspace_for_owner,
)
from .network_endpoints import interfaces_for_scope
from .network_inventory import devices_for_scope
from .scoping import DataScope
from .sites import locations_for_scope, sites_for_scope


class NetworkCircuitError(ValueError):
    pass


def _validate(record) -> None:  # type: ignore[no-untyped-def]
    try:
        record.full_clean()
    except ValidationError as exc:
        raise NetworkCircuitError(" ".join(exc.messages)) from exc


def _scope(tenant: Tenant, organization: Organization | None) -> DataScope:
    return DataScope.organization(tenant, organization) if organization is not None else DataScope.tenant(tenant)


def circuits_for_scope(scope: DataScope) -> QuerySet[NetworkCircuit]:
    return (
        NetworkCircuit.scoped.for_scope(scope)
        .select_related("entity", "provider__entity", "contract__entity")
        .prefetch_related(
            Prefetch(
                "handoffs",
                queryset=NetworkCircuitHandoff.objects.select_related(
                    "entity", "site__entity", "location__entity", "device__entity", "interface__entity"
                ),
            )
        )
    )


def handoffs_for_scope(scope: DataScope) -> QuerySet[NetworkCircuitHandoff]:
    return NetworkCircuitHandoff.scoped.for_scope(scope).select_related(
        "entity", "circuit__entity", "site__entity", "location__entity", "device__entity", "interface__entity"
    )


def circuit_choices(scope: DataScope, *, include_contracts: bool) -> dict[str, QuerySet[Any]]:
    return {
        "providers": provider_choices(Tenant.objects.get(pk=scope.tenant_id)),
        "contracts": contracts_for_scope(scope) if include_contracts else CommercialContract.objects.none(),
        "sites": sites_for_scope(scope),
        "locations": locations_for_scope(scope),
        "devices": devices_for_scope(scope),
        "interfaces": interfaces_for_scope(scope),
    }


def _provider(tenant: Tenant, entity_id: UUID) -> Organization:
    provider = provider_choices(tenant).filter(entity_id=entity_id).first()
    if provider is None:
        raise NetworkCircuitError("The selected provider is unavailable.")
    return provider


def _contract(scope: DataScope, entity_id: UUID | None) -> CommercialContract | None:
    if entity_id is None:
        return None
    contract = contracts_for_scope(scope).filter(entity_id=entity_id).first()
    if contract is None:
        raise NetworkCircuitError("The selected contract is unavailable in this Workspace.")
    return contract


def _related(scope: DataScope, model, entity_id: UUID | None, label: str):  # type: ignore[no-untyped-def]
    if entity_id is None:
        return None
    try:
        return model.scoped.for_scope(scope).get(entity_id=entity_id)
    except model.DoesNotExist as exc:
        raise NetworkCircuitError(f"The selected {label} is unavailable in this Workspace.") from exc


def _lock(scope: DataScope) -> None:
    if connection.vendor == "postgresql":
        key = f"circuits:{scope.tenant_id}:{scope.organization_id or 'msp'}"
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])


@transaction.atomic
def create_circuit(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    name: str,
    provider_entity_id: UUID,
    contract_entity_id: UUID | None,
    service_identifier: str,
    kind: str,
    status: str,
    bandwidth_down_mbps: Decimal | None,
    bandwidth_up_mbps: Decimal | None,
    installed_on: date | None,
    service_starts_on: date | None,
    review_on: date | None,
    planned_disconnect_on: date | None,
    description: str,
) -> NetworkCircuit:
    scope = _scope(tenant, organization)
    _lock(scope)
    provider = _provider(tenant, provider_entity_id)
    contract = _contract(scope, contract_entity_id)
    entity = Entity.objects.create(
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type="network_circuit",
        display_name=name.strip(),
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    record = NetworkCircuit(
        tenant=tenant,
        organization=organization,
        entity=entity,
        provider=provider,
        contract=contract,
        service_identifier=service_identifier.strip(),
        kind=kind,
        status=status,
        bandwidth_down_mbps=bandwidth_down_mbps,
        bandwidth_up_mbps=bandwidth_up_mbps,
        installed_on=installed_on,
        service_starts_on=service_starts_on,
        review_on=review_on,
        planned_disconnect_on=planned_disconnect_on,
        description=description,
    )
    _validate(record)
    record.save()
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="network_circuit.created", entity_id=entity.id, metadata={}
    )
    return circuits_for_scope(scope).get(pk=record.pk)


@transaction.atomic
def update_circuit(*, record: NetworkCircuit, actor_id: UUID, values: dict[str, object]) -> NetworkCircuit:
    scope = _scope(record.tenant, record.organization)
    _lock(scope)
    locked = NetworkCircuit.objects.select_for_update().select_related("entity").get(pk=record.pk)
    if "name" in values:
        locked.entity.display_name = str(values.pop("name")).strip()
        locked.entity.full_clean()
        locked.entity.save(update_fields=("display_name", "updated_at"))
    if "provider_entity_id" in values:
        locked.provider = _provider(locked.tenant, values.pop("provider_entity_id"))  # type: ignore[arg-type]
    if "contract_entity_id" in values:
        locked.contract = _contract(scope, values.pop("contract_entity_id"))  # type: ignore[arg-type]
    for key, value in values.items():
        setattr(locked, key, value.strip() if key == "service_identifier" and isinstance(value, str) else value)
    _validate(locked)
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="network_circuit.updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return circuits_for_scope(scope).get(pk=locked.pk)


@transaction.atomic
def create_handoff(
    *,
    circuit: NetworkCircuit,
    actor_id: UUID,
    name: str,
    side: str,
    media: str,
    connector: str,
    provider_reference: str,
    site_entity_id: UUID | None,
    location_entity_id: UUID | None,
    device_entity_id: UUID | None,
    interface_entity_id: UUID | None,
    description: str,
) -> NetworkCircuitHandoff:
    scope = _scope(circuit.tenant, circuit.organization)
    locked = NetworkCircuit.objects.select_for_update().get(pk=circuit.pk)
    entity = Entity.objects.create(
        tenant=locked.tenant,
        workspace=workspace_for_owner(tenant=locked.tenant, organization=locked.organization),
        organization=locked.organization,
        entity_type="network_circuit_handoff",
        display_name=name.strip(),
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    handoff = NetworkCircuitHandoff(
        tenant=locked.tenant,
        organization=locked.organization,
        entity=entity,
        circuit=locked,
        side=side,
        media=media,
        connector=connector.strip(),
        provider_reference=provider_reference.strip(),
        site=_related(scope, Site, site_entity_id, "site"),
        location=_related(scope, Location, location_entity_id, "location"),
        device=_related(scope, NetworkDevice, device_entity_id, "device"),
        interface=_related(scope, NetworkInterface, interface_entity_id, "interface"),
        description=description,
    )
    _validate(handoff)
    handoff.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="network_circuit.handoff_created",
        entity_id=locked.entity_id,
        metadata={"handoff_id": str(entity.id)},
    )
    return handoffs_for_scope(scope).get(pk=handoff.pk)


@transaction.atomic
def update_handoff(
    *, handoff: NetworkCircuitHandoff, actor_id: UUID, values: dict[str, object]
) -> NetworkCircuitHandoff:
    scope = _scope(handoff.tenant, handoff.organization)
    locked = NetworkCircuitHandoff.objects.select_for_update().select_related("entity", "circuit").get(pk=handoff.pk)
    if "name" in values:
        locked.entity.display_name = str(values.pop("name")).strip()
        locked.entity.full_clean()
        locked.entity.save(update_fields=("display_name", "updated_at"))
    for field, model, label in (
        ("site_entity_id", Site, "site"),
        ("location_entity_id", Location, "location"),
        ("device_entity_id", NetworkDevice, "device"),
        ("interface_entity_id", NetworkInterface, "interface"),
    ):
        if field in values:
            setattr(
                locked,
                field.removesuffix("_entity_id"),
                _related(scope, model, cast(UUID | None, values.pop(field)), label),
            )
    for key, value in values.items():
        setattr(
            locked,
            key,
            value.strip() if key in {"connector", "provider_reference"} and isinstance(value, str) else value,
        )
    _validate(locked)
    locked.save()
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="network_circuit.handoff_updated",
        entity_id=locked.circuit.entity_id,
        metadata={"handoff_id": str(locked.entity_id)},
    )
    return handoffs_for_scope(scope).get(pk=locked.pk)


def lifecycle_events(record: NetworkCircuit, *, include_contract: bool, today: date) -> list[dict[str, object]]:
    candidates: list[tuple[str, date, str]] = []
    if record.review_on:
        candidates.append(("review", record.review_on, "Review circuit"))
    if record.planned_disconnect_on:
        candidates.append(("disconnect", record.planned_disconnect_on, "Planned disconnect"))
    contract = record.contract if include_contract and record.contract_id else None
    if contract is not None:
        if contract.renews_on:
            if contract.renewal_notice_days:
                candidates.append(
                    (
                        "renewal_notice",
                        contract.renews_on - timedelta(days=contract.renewal_notice_days),
                        "Renewal notice deadline",
                    )
                )
            candidates.append(("renewal", contract.renews_on, "Contract renewal"))
        if contract.ends_on:
            candidates.append(("contract_end", contract.ends_on, "Contract end"))
    return [
        {
            "kind": kind,
            "date": event_date,
            "label": label,
            "state": "overdue" if event_date < today else "today" if event_date == today else "upcoming",
        }
        for kind, event_date, label in sorted(candidates, key=lambda item: (item[1], item[0]))
    ]
