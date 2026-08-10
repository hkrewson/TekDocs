from __future__ import annotations

from typing import cast
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Prefetch, QuerySet
from django.utils import timezone

from .models import (
    AuditEvent,
    ClientAsset,
    ClientSoftwareInstallation,
    Entity,
    EntityVisibility,
    Organization,
    PersonAssociation,
    Site,
    SoftwareInstallationStatus,
    SoftwareLicense,
    SoftwareLicenseEvent,
    SoftwareLicenseEventType,
    SoftwareLicenseInstallation,
    SoftwareLicenseSeat,
    Tenant,
)
from .scoping import DataScope


class SoftwareInventoryError(Exception):
    pass


def _validate(record) -> None:  # type: ignore[no-untyped-def]
    try:
        record.full_clean()
    except ValidationError as exc:
        raise SoftwareInventoryError(" ".join(exc.messages)) from exc


def installations_for_scope(scope: DataScope) -> QuerySet[ClientSoftwareInstallation]:
    return (
        ClientSoftwareInstallation.scoped.for_scope(scope)
        .select_related("asset__entity", "asset__product__entity", "asset__model__entity", "site__entity")
        .filter(asset__archived_at__isnull=True, asset__entity__archived_at__isnull=True)
        .order_by("asset__entity__display_name")
    )


def licenses_for_scope(scope: DataScope) -> QuerySet[SoftwareLicense]:
    return (
        SoftwareLicense.scoped.for_scope(scope)
        .filter(archived_at__isnull=True, entity__archived_at__isnull=True)
        .select_related("entity", "supplier__entity", "product__entity", "model__entity")
        .prefetch_related(
            Prefetch(
                "installation_links",
                queryset=SoftwareLicenseInstallation.objects.filter(archived_at__isnull=True).select_related(
                    "installation__asset__entity"
                ),
            ),
            Prefetch(
                "seats",
                queryset=SoftwareLicenseSeat.objects.select_related(
                    "person__person__entity", "installation__asset__entity"
                ).order_by("seat_number"),
            ),
            Prefetch(
                "events",
                queryset=SoftwareLicenseEvent.objects.select_related(
                    "person__person__entity", "installation__asset__entity"
                ),
            ),
        )
    )


def installation_choices(scope: DataScope) -> tuple[QuerySet[ClientSoftwareInstallation], QuerySet[PersonAssociation]]:
    installations = installations_for_scope(scope)
    people = (
        PersonAssociation.scoped.for_scope(scope)
        .filter(archived_at__isnull=True, person__entity__archived_at__isnull=True)
        .select_related("person__entity")
        .order_by("person__entity__display_name")
    )
    return installations, people


def _installation(asset: ClientAsset, *, lock: bool = False) -> ClientSoftwareInstallation:
    if asset.product.kind != "software":
        raise SoftwareInventoryError("Software installation is available only for software assets.")
    query = (
        ClientSoftwareInstallation.objects.select_for_update(of=("self",))
        if lock
        else ClientSoftwareInstallation.objects
    )
    try:
        return query.select_related("asset__product", "site__entity").get(asset=asset)
    except ClientSoftwareInstallation.DoesNotExist as exc:
        raise SoftwareInventoryError("The software installation is unavailable.") from exc


@transaction.atomic
def update_installation(*, asset: ClientAsset, actor_id: UUID, values: dict[str, object]) -> ClientSoftwareInstallation:
    installation = _installation(ClientAsset.objects.select_for_update().get(pk=asset.pk), lock=True)
    if installation.status == SoftwareInstallationStatus.UNINSTALLED:
        raise SoftwareInventoryError("Uninstalled software cannot be edited.")
    site_id = cast(UUID | None, values.pop("site_id", None)) if "site_id" in values else installation.site_id
    site = None
    if site_id:
        site = Site.objects.filter(
            id=site_id, tenant=asset.tenant, organization=asset.organization, archived_at__isnull=True
        ).first()
        if site is None:
            raise SoftwareInventoryError("The installation site is unavailable.")
    for field, value in values.items():
        setattr(installation, field, value.strip() if isinstance(value, str) else value)
    installation.site = site
    _validate(installation)
    installation.save()
    AuditEvent.objects.create(
        tenant=installation.tenant,
        actor_id=actor_id,
        action="asset.software.updated",
        entity_id=asset.entity_id,
        metadata={},
    )
    return _installation(asset)


@transaction.atomic
def create_license(
    *, tenant: Tenant, organization: Organization, actor_id: UUID, asset: ClientAsset, values: dict[str, object]
) -> SoftwareLicense:
    installation = _installation(asset)
    entity = Entity.objects.create(
        tenant=tenant,
        organization=organization,
        entity_type="software_license",
        display_name=str(values.pop("name")).strip(),
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    license_record = SoftwareLicense(
        tenant=tenant,
        organization=organization,
        entity=entity,
        supplier=asset.supplier,
        product=asset.product,
        model=asset.model,
        created_by_id=actor_id,
        **values,
    )
    _validate(license_record)
    license_record.save()
    link = SoftwareLicenseInstallation(
        tenant=tenant, organization=organization, license=license_record, installation=installation
    )
    _validate(link)
    link.save()
    SoftwareLicenseEvent.objects.create(
        tenant=tenant,
        organization=organization,
        license=license_record,
        event_type=SoftwareLicenseEventType.CREATED,
        installation=installation,
        actor_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="software_license.created", entity_id=entity.id, metadata={}
    )
    return licenses_for_scope(DataScope.organization(tenant, organization)).get(pk=license_record.pk)


@transaction.atomic
def update_license(*, license_record: SoftwareLicense, actor_id: UUID, values: dict[str, object]) -> SoftwareLicense:
    locked = SoftwareLicense.objects.select_for_update().get(pk=license_record.pk)
    entity = Entity.objects.select_for_update().get(pk=locked.entity_id)
    active_seats = locked.seats.filter(revoked_at__isnull=True).count()
    if "seat_limit" in values and int(str(values["seat_limit"])) < active_seats:
        raise SoftwareInventoryError("Seat limit cannot be lower than the active assignment count.")
    name = values.pop("name", None)
    for field, value in values.items():
        setattr(locked, field, value.strip() if isinstance(value, str) else value)
    _validate(locked)
    locked.save()
    if name is not None:
        entity.display_name = str(name).strip()
        entity.full_clean()
        entity.save(update_fields=("display_name", "updated_at"))
    SoftwareLicenseEvent.objects.create(
        tenant=locked.tenant,
        organization=locked.organization,
        license=locked,
        event_type=SoftwareLicenseEventType.DETAILS_UPDATED,
        actor_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="software_license.updated",
        entity_id=locked.entity_id,
        metadata={},
    )
    return licenses_for_scope(DataScope.organization(locked.tenant, locked.organization)).get(pk=locked.pk)


@transaction.atomic
def link_installation(*, license_record: SoftwareLicense, installation_id: UUID, actor_id: UUID) -> SoftwareLicense:
    locked = SoftwareLicense.objects.select_for_update().get(pk=license_record.pk)
    installation = (
        ClientSoftwareInstallation.objects.filter(
            id=installation_id, tenant=locked.tenant, organization=locked.organization
        )
        .select_related("asset")
        .first()
    )
    if installation is None:
        raise SoftwareInventoryError("The software installation is unavailable.")
    link, created = SoftwareLicenseInstallation.objects.get_or_create(
        license=locked,
        installation=installation,
        defaults={"tenant": locked.tenant, "organization": locked.organization},
    )
    if not created and link.archived_at is None:
        return licenses_for_scope(DataScope.organization(locked.tenant, locked.organization)).get(pk=locked.pk)
    link.archived_at = None
    _validate(link)
    link.save()
    SoftwareLicenseEvent.objects.create(
        tenant=locked.tenant,
        organization=locked.organization,
        license=locked,
        event_type=SoftwareLicenseEventType.INSTALLATION_LINKED,
        installation=installation,
        actor_id=actor_id,
    )
    return licenses_for_scope(DataScope.organization(locked.tenant, locked.organization)).get(pk=locked.pk)


@transaction.atomic
def assign_seat(
    *,
    license_record: SoftwareLicense,
    actor_id: UUID,
    person_id: UUID | None = None,
    installation_id: UUID | None = None,
) -> SoftwareLicense:
    locked = SoftwareLicense.objects.select_for_update().get(pk=license_record.pk)
    if locked.status != "active":
        raise SoftwareInventoryError("Seats can be assigned only from an active license.")
    active = locked.seats.filter(revoked_at__isnull=True)
    if active.count() >= locked.seat_limit:
        raise SoftwareInventoryError("No seats are available on this license.")
    person = (
        PersonAssociation.objects.filter(
            id=person_id, tenant=locked.tenant, organization=locked.organization, archived_at__isnull=True
        ).first()
        if person_id
        else None
    )
    installation = (
        ClientSoftwareInstallation.objects.filter(
            id=installation_id, tenant=locked.tenant, organization=locked.organization
        )
        .select_related("asset")
        .first()
        if installation_id
        else None
    )
    if (person_id and person is None) or (installation_id and installation is None):
        raise SoftwareInventoryError("The seat assignment target is unavailable.")
    if person is None and installation is None:
        raise SoftwareInventoryError("Choose a person or installation for the seat.")
    if (
        installation
        and not locked.installation_links.filter(installation=installation, archived_at__isnull=True).exists()
    ):
        raise SoftwareInventoryError("Link the installation to this license before assigning its seat.")
    if person and active.filter(person=person).exists():
        raise SoftwareInventoryError("This person already has an active seat.")
    if installation and active.filter(installation=installation).exists():
        raise SoftwareInventoryError("This installation already has an active seat.")
    seat_number = (locked.seats.aggregate(maximum=Max("seat_number"))["maximum"] or 0) + 1
    seat = SoftwareLicenseSeat(
        tenant=locked.tenant,
        organization=locked.organization,
        license=locked,
        seat_number=seat_number,
        person=person,
        installation=installation,
    )
    _validate(seat)
    seat.save()
    SoftwareLicenseEvent.objects.create(
        tenant=locked.tenant,
        organization=locked.organization,
        license=locked,
        event_type=SoftwareLicenseEventType.SEAT_ASSIGNED,
        installation=installation,
        person=person,
        seat_number=seat_number,
        actor_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="software_license.seat_assigned",
        entity_id=locked.entity_id,
        metadata={},
    )
    return licenses_for_scope(DataScope.organization(locked.tenant, locked.organization)).get(pk=locked.pk)


@transaction.atomic
def revoke_seat(*, license_record: SoftwareLicense, seat_id: UUID, actor_id: UUID) -> SoftwareLicense:
    locked = SoftwareLicense.objects.select_for_update().get(pk=license_record.pk)
    seat = locked.seats.select_for_update().filter(id=seat_id, revoked_at__isnull=True).first()
    if seat is None:
        raise SoftwareInventoryError("The active seat is unavailable.")
    seat.revoked_at = timezone.now()
    seat.save(update_fields=("revoked_at",))
    SoftwareLicenseEvent.objects.create(
        tenant=locked.tenant,
        organization=locked.organization,
        license=locked,
        event_type=SoftwareLicenseEventType.SEAT_REVOKED,
        installation=seat.installation,
        person=seat.person,
        seat_number=seat.seat_number,
        actor_id=actor_id,
    )
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="software_license.seat_revoked",
        entity_id=locked.entity_id,
        metadata={},
    )
    return licenses_for_scope(DataScope.organization(locked.tenant, locked.organization)).get(pk=locked.pk)
