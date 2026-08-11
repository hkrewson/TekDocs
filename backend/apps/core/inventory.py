from __future__ import annotations

import hashlib
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q, QuerySet
from django.utils import timezone

from .models import (
    AuditEvent,
    CatalogModel,
    CatalogModelRevision,
    CatalogProduct,
    CatalogProductDocument,
    ClientAsset,
    ClientAssetDocumentProvenance,
    ClientAssetLifecycleEvent,
    ClientHardwareAsset,
    ClientSoftwareInstallation,
    DocumentPublication,
    DocumentPublicationArtifact,
    Entity,
    EntityVisibility,
    HardwareLifecycleEventType,
    HardwareLifecycleState,
    Location,
    Organization,
    PersonAssociation,
    PublicationAudience,
    Site,
    Tenant,
    workspace_for_owner,
)
from .publications import canonical_json, verify_publication
from .scoping import DataScope


class InventoryError(Exception):
    pass


MAX_BULK_ASSETS = 100


def require_operational_owner(organization: Organization | None) -> None:
    if organization is None:
        return
    classifications = {item.kind for item in organization.classifications.all()}
    if "client" not in classifications:
        raise InventoryError("Client assets require a client organization workspace.")


require_client = require_operational_owner


def _checksum(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _document_prefetch() -> Prefetch[
    str,
    QuerySet[ClientAssetDocumentProvenance, ClientAssetDocumentProvenance],
    str,
]:
    return Prefetch(
        "document_provenance",
        queryset=ClientAssetDocumentProvenance.objects.select_related(
            "catalog_document",
            "publication",
            "publication__entity",
            "publication__document",
            "publication__document__entity",
        ).prefetch_related(
            Prefetch(
                "publication__artifacts",
                queryset=DocumentPublicationArtifact.objects.select_related("entity").order_by("kind", "id"),
            )
        ),
    )


def assets_for_scope(scope: DataScope) -> QuerySet[ClientAsset]:
    return (
        ClientAsset.scoped.for_scope(scope)
        .filter(archived_at__isnull=True, entity__archived_at__isnull=True)
        .select_related(
            "entity",
            "organization",
            "supplier",
            "supplier__entity",
            "product",
            "product__entity",
            "model",
            "model__entity",
            "model_revision",
            "specification_version",
            "specification_version__definition",
            "created_by",
            "hardware",
            "hardware__assigned_person",
            "hardware__assigned_person__person__entity",
            "hardware__assigned_site__entity",
            "hardware__assigned_location__entity",
            "software_installation",
            "software_installation__site__entity",
        )
        .prefetch_related(
            _document_prefetch(),
            "lifecycle_events__person__person__entity",
            "lifecycle_events__site__entity",
            "lifecycle_events__location__entity",
        )
    )


@transaction.atomic
def bulk_update_assets(
    *,
    scope: DataScope,
    actor_id: UUID,
    asset_entity_ids: list[UUID],
    action: str,
    lifecycle_state: str | None = None,
) -> int:
    requested = set(asset_entity_ids)
    if not requested or len(requested) != len(asset_entity_ids) or len(requested) > MAX_BULK_ASSETS:
        raise InventoryError("Choose between 1 and 100 unique assets.")
    assets = list(
        assets_for_scope(scope)
        .select_for_update(of=("self",))
        .filter(entity_id__in=requested)
        .order_by("entity_id")
    )
    if len(assets) != len(requested):
        raise InventoryError("One or more selected assets are unavailable in this workspace.")

    if action == "set_hardware_state":
        if lifecycle_state not in {
            HardwareLifecycleState.IN_STOCK,
            HardwareLifecycleState.IN_SERVICE,
            HardwareLifecycleState.REPAIR,
            HardwareLifecycleState.RETIRED,
        }:
            raise InventoryError("Choose a supported non-disposal hardware state.")
        profiles: list[ClientHardwareAsset] = []
        for asset in assets:
            profile = _hardware(asset, lock=True)
            if profile.lifecycle_state == HardwareLifecycleState.DISPOSED:
                raise InventoryError("Disposed hardware cannot be changed by a bulk action.")
            profiles.append(profile)
        for asset, profile in zip(assets, profiles, strict=True):
            previous = profile.lifecycle_state
            if previous == lifecycle_state:
                continue
            profile.lifecycle_state = lifecycle_state
            _validate_profile(profile)
            profile.save(update_fields=("lifecycle_state", "updated_at"))
            _append_event(profile, HardwareLifecycleEventType.STATE_CHANGED, actor_id, from_state=previous)
            AuditEvent.objects.create(
                tenant=asset.tenant,
                actor_id=actor_id,
                action="asset.hardware.state_changed",
                entity_id=asset.entity_id,
                metadata={},
            )
        return len(assets)

    if action == "archive":
        for asset in assets:
            installation = getattr(asset, "software_installation", None)
            if installation is not None and (
                installation.license_links.filter(archived_at__isnull=True).exists()
                or installation.license_seats.filter(revoked_at__isnull=True).exists()
            ):
                raise InventoryError("Unlink active license coverage and seats before archiving software assets.")
        archived_at = timezone.now()
        for asset in assets:
            ClientAsset.objects.filter(pk=asset.pk, archived_at__isnull=True).update(
                archived_at=archived_at,
                updated_at=archived_at,
            )
            Entity.objects.filter(pk=asset.entity_id, archived_at__isnull=True).update(
                archived_at=archived_at,
                updated_at=archived_at,
            )
            AuditEvent.objects.create(
                tenant=asset.tenant,
                actor_id=actor_id,
                action="asset.archived",
                entity_id=asset.entity_id,
                metadata={},
            )
        return len(assets)

    raise InventoryError("Unsupported bulk asset action.")


def model_choices_for_client(scope: DataScope, *, query: str = "") -> QuerySet[CatalogModel]:
    records = (
        CatalogModel.objects.filter(
            tenant_id=scope.tenant_id,
            archived_at__isnull=True,
            entity__archived_at__isnull=True,
            product__archived_at__isnull=True,
            organization__classifications__kind__in=("vendor", "manufacturer"),
        )
        .select_related("entity", "organization", "organization__entity", "product", "product__entity")
        .prefetch_related(
            Prefetch(
                "revisions",
                queryset=CatalogModelRevision.objects.select_related(
                    "specification_version", "specification_version__definition"
                ).order_by("revision"),
            )
        )
        .distinct()
    )
    if query:
        records = records.filter(
            Q(entity__display_name__icontains=query)
            | Q(model_number__icontains=query)
            | Q(product__entity__display_name__icontains=query)
            | Q(organization__entity__display_name__icontains=query)
        )
    return records.order_by(
        "organization__entity__display_name", "product__entity__display_name", "entity__display_name"
    )


def eligible_publications_for_supplier(scope: DataScope) -> QuerySet[DocumentPublication]:
    if scope.organization_id is None:
        return DocumentPublication.objects.none()
    return (
        DocumentPublication.scoped.for_scope(scope)
        .filter(audience=PublicationAudience.CLIENT_VISIBLE)
        .select_related("entity", "document", "document__entity")
        .prefetch_related(Prefetch("artifacts", queryset=DocumentPublicationArtifact.objects.select_related("entity")))
        .order_by("title", "-published_at")
    )


def product_documents(product: CatalogProduct) -> QuerySet[CatalogProductDocument]:
    return (
        CatalogProductDocument.objects.filter(product=product, archived_at__isnull=True)
        .select_related("model", "model__entity", "publication", "publication__entity", "publication__document__entity")
        .order_by("publication__title", "id")
    )


@transaction.atomic
def associate_product_document(
    *,
    product: CatalogProduct,
    publication: DocumentPublication,
    actor_id: UUID,
    model: CatalogModel | None = None,
) -> CatalogProductDocument:
    locked_product = CatalogProduct.objects.select_for_update().get(pk=product.pk)
    # Publications are append-only and cannot be update-locked by the restricted
    # runtime role. Their immutable manifest is safe to verify with a normal read.
    locked_publication = DocumentPublication.objects.select_related("document").get(pk=publication.pk)
    locked_model = CatalogModel.objects.select_for_update().get(pk=model.pk) if model is not None else None
    if locked_product.archived_at is not None:
        raise InventoryError("Archived products cannot receive documentation.")
    if locked_model is not None and (
        locked_model.archived_at is not None
        or locked_model.product_id != locked_product.id
        or locked_model.organization_id != locked_product.organization_id
    ):
        raise InventoryError("The selected model does not belong to this active product.")
    if (
        locked_publication.tenant_id != locked_product.tenant_id
        or locked_publication.organization_id != locked_product.organization_id
        or locked_publication.audience != PublicationAudience.CLIENT_VISIBLE
    ):
        raise InventoryError("Choose a client-visible STATIC publication owned by this supplier.")
    if not verify_publication(locked_publication)["valid"]:
        raise InventoryError("The selected STATIC publication did not pass verification.")
    try:
        association = CatalogProductDocument.objects.create(
            tenant=locked_product.tenant,
            organization=locked_product.organization,
            product=locked_product,
            model=locked_model,
            publication=locked_publication,
            created_by_id=actor_id,
        )
    except IntegrityError as exc:
        raise InventoryError("This publication is already associated with the selected product scope.") from exc
    association.full_clean()
    AuditEvent.objects.create(
        tenant=locked_product.tenant,
        actor_id=actor_id,
        action="catalog.document.associated",
        entity_id=locked_product.entity_id,
        metadata={},
    )
    return association


@transaction.atomic
def archive_product_document(*, association: CatalogProductDocument, actor_id: UUID) -> None:
    locked = CatalogProductDocument.objects.select_for_update().get(pk=association.pk)
    if locked.archived_at is not None:
        return
    from django.utils import timezone

    locked.archived_at = timezone.now()
    locked.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=locked.tenant,
        actor_id=actor_id,
        action="catalog.document.archived",
        entity_id=locked.product.entity_id,
        metadata={},
    )


@transaction.atomic
def create_client_asset(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    model_entity_id: UUID,
    name: str,
    entity_id: UUID | None = None,
) -> ClientAsset:
    require_operational_owner(organization)
    # Supplier catalog rows are a read-only RLS projection in client context.
    # Revisions and publication manifests are immutable, so exact identifiers and
    # checksums provide the snapshot boundary without cross-workspace write locks.
    model = (
        CatalogModel.objects.select_related("entity", "organization", "product", "product__entity")
        .get(
            tenant=tenant,
            entity_id=model_entity_id,
            archived_at__isnull=True,
            entity__archived_at__isnull=True,
            product__archived_at__isnull=True,
        )
    )
    supplier_classifications = {item.kind for item in model.organization.classifications.all()}
    if not supplier_classifications.intersection({"vendor", "manufacturer"}):
        raise InventoryError("The selected model no longer belongs to an active supplier.")
    revision = (
        CatalogModelRevision.objects.select_related("specification_version")
        .filter(model=model)
        .order_by("-revision")
        .first()
    )
    if revision is None:
        raise InventoryError("The selected model has no retained revision.")
    payload = {
        "supplier_id": str(model.organization.entity_id),
        "product_id": str(model.product.entity_id),
        "model_id": str(model.entity_id),
        "model_revision_id": str(revision.id),
        "specification_version_id": str(revision.specification_version_id),
        "specifications": revision.specifications,
    }
    display_name = name.strip() or model.entity.display_name
    entity_values: dict[str, object] = {}
    if entity_id is not None:
        entity_values["id"] = entity_id
    entity = Entity.objects.create(
        **entity_values,
        tenant=tenant,
        workspace=workspace_for_owner(tenant=tenant, organization=organization),
        organization=organization,
        entity_type="client_asset",
        display_name=display_name,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    asset = ClientAsset.objects.create(
        tenant=tenant,
        organization=organization,
        entity=entity,
        supplier=model.organization,
        product=model.product,
        model=model,
        model_revision=revision,
        specification_version=revision.specification_version,
        specifications=revision.specifications,
        provenance_checksum=_checksum(payload),
        created_by_id=actor_id,
    )
    if model.product.kind == "hardware":
        ClientHardwareAsset.objects.create(tenant=tenant, organization=organization, asset=asset)
        ClientAssetLifecycleEvent.objects.create(
            tenant=tenant,
            organization=organization,
            asset=asset,
            event_type=HardwareLifecycleEventType.CREATED,
            to_state=HardwareLifecycleState.IN_STOCK,
            actor_id=actor_id,
        )
    else:
        ClientSoftwareInstallation.objects.create(
            tenant=tenant,
            organization=organization,
            asset=asset,
        )
    associations = list(
        CatalogProductDocument.objects.filter(
            tenant=tenant,
            organization=model.organization,
            product=model.product,
            archived_at__isnull=True,
        )
        .filter(Q(model__isnull=True) | Q(model=model))
        .select_related("publication")
        .order_by("publication_id")
    )
    seen_publications: set[UUID] = set()
    for association in associations:
        publication = association.publication
        if publication.id in seen_publications:
            continue
        if not verify_publication(publication)["valid"]:
            raise InventoryError("An associated STATIC publication did not pass verification.")
        provenance = ClientAssetDocumentProvenance(
            tenant=tenant,
            organization=organization,
            asset=asset,
            catalog_document=association,
            publication=publication,
            content_digest=publication.content_digest,
        )
        provenance.full_clean()
        provenance.save()  # type: ignore[no-untyped-call]
        seen_publications.add(publication.id)
    AuditEvent.objects.create(
        tenant=tenant,
        actor_id=actor_id,
        action="asset.created_from_catalog",
        entity_id=asset.entity_id,
        metadata={},
    )
    scope = DataScope.organization(tenant, organization) if organization is not None else DataScope.tenant(tenant)
    return assets_for_scope(scope).get(pk=asset.pk)


def _hardware(asset: ClientAsset, *, lock: bool = False) -> ClientHardwareAsset:
    if asset.product.kind != "hardware":
        raise InventoryError("Hardware lifecycle is available only for hardware assets.")
    query = ClientHardwareAsset.objects.select_for_update(of=("self",)) if lock else ClientHardwareAsset.objects
    try:
        return query.select_related(
            "asset__product", "assigned_person__person__entity", "assigned_site__entity", "assigned_location__entity"
        ).get(asset=asset)
    except ClientHardwareAsset.DoesNotExist as exc:
        raise InventoryError("The hardware profile is unavailable.") from exc


def lifecycle_events(asset: ClientAsset) -> QuerySet[ClientAssetLifecycleEvent]:
    return ClientAssetLifecycleEvent.objects.filter(asset=asset).select_related(
        "person__person__entity", "site__entity", "location__entity", "actor"
    )


def assignment_choices(asset: ClientAsset) -> tuple[QuerySet[PersonAssociation], QuerySet[Site], QuerySet[Location]]:
    base = {"tenant": asset.tenant, "organization": asset.organization, "archived_at__isnull": True}
    people = PersonAssociation.objects.filter(
        **base, person__entity__archived_at__isnull=True
    ).select_related("person__entity")
    sites = Site.objects.filter(**base, entity__archived_at__isnull=True).select_related("entity")
    locations = Location.objects.filter(**base, entity__archived_at__isnull=True).select_related(
        "entity", "site__entity"
    )
    return (
        people.order_by("person__entity__display_name"),
        sites.order_by("entity__display_name"),
        locations.order_by("site__entity__display_name", "entity__display_name"),
    )


def _normalize_identifier(value: str) -> str:
    return " ".join(value.strip().split()).upper()


def _validate_profile(profile: ClientHardwareAsset) -> None:
    try:
        profile.full_clean()
    except ValidationError as exc:
        raise InventoryError(" ".join(exc.messages)) from exc


def _append_event(  # type: ignore[no-untyped-def]
    profile: ClientHardwareAsset,
    event_type: str,
    actor_id: UUID,
    *,
    from_state: str = "",
    person=None,
    site=None,
    location=None,
) -> None:
    event = ClientAssetLifecycleEvent(
        tenant=profile.tenant,
        organization=profile.organization,
        asset=profile.asset,
        event_type=event_type,
        from_state=from_state,
        to_state=profile.lifecycle_state,
        person=person,
        site=site,
        location=location,
        actor_id=actor_id,
    )
    event.full_clean()
    event.save()  # type: ignore[no-untyped-call]


@transaction.atomic
def update_hardware_details(*, asset: ClientAsset, actor_id: UUID, values: dict[str, object]) -> ClientHardwareAsset:
    profile = _hardware(ClientAsset.objects.select_for_update().get(pk=asset.pk), lock=True)
    if profile.lifecycle_state == HardwareLifecycleState.DISPOSED:
        raise InventoryError("Disposed hardware cannot be edited.")
    old_state = profile.lifecycle_state
    for field, value in values.items():
        if field in {"serial_number", "asset_tag"}:
            value = _normalize_identifier(str(value))
        setattr(profile, field, value)
    _validate_profile(profile)
    try:
        profile.save()
    except IntegrityError as exc:
        raise InventoryError("Serial number and asset tag must be unique within this workspace.") from exc
    event_type = (
        HardwareLifecycleEventType.STATE_CHANGED
        if profile.lifecycle_state != old_state
        else HardwareLifecycleEventType.DETAILS_UPDATED
    )
    _append_event(profile, event_type, actor_id, from_state=old_state)
    AuditEvent.objects.create(
        tenant=profile.tenant,
        actor_id=actor_id,
        action=f"asset.hardware.{event_type}",
        entity_id=asset.entity_id,
        metadata={},
    )
    return _hardware(asset)


@transaction.atomic
def assign_hardware(  # type: ignore[no-untyped-def]
    *, asset: ClientAsset, actor_id: UUID, person_id=None, site_id=None, location_id=None
) -> ClientHardwareAsset:
    profile = _hardware(ClientAsset.objects.select_for_update().get(pk=asset.pk), lock=True)
    if profile.lifecycle_state == HardwareLifecycleState.DISPOSED:
        raise InventoryError("Disposed hardware cannot be assigned.")
    if not any((person_id, site_id, location_id)):
        raise InventoryError("Choose a person, site, or location for this assignment.")
    scope = {"tenant": asset.tenant, "organization": asset.organization, "archived_at__isnull": True}
    person = (
        PersonAssociation.objects.filter(
            **scope, id=person_id, person__entity__archived_at__isnull=True
        ).first()
        if person_id
        else None
    )
    site = Site.objects.filter(**scope, id=site_id, entity__archived_at__isnull=True).first() if site_id else None
    location = (
        Location.objects.filter(**scope, id=location_id, entity__archived_at__isnull=True).first()
        if location_id
        else None
    )
    if (person_id and person is None) or (site_id and site is None) or (location_id and location is None):
        raise InventoryError("The assignment target is unavailable.")
    if location is not None:
        if site is None:
            site = location.site
        elif location.site_id != site.id:
            raise InventoryError("The location does not belong to the selected site.")
    if profile.assigned_person_id or profile.assigned_site_id or profile.assigned_location_id:
        _append_event(
            profile,
            HardwareLifecycleEventType.UNASSIGNED,
            actor_id,
            person=profile.assigned_person,
            site=profile.assigned_site,
            location=profile.assigned_location,
        )
    profile.assigned_person, profile.assigned_site, profile.assigned_location = person, site, location
    profile.assigned_at = timezone.now()
    if profile.lifecycle_state == HardwareLifecycleState.IN_STOCK:
        profile.lifecycle_state = HardwareLifecycleState.IN_SERVICE
    _validate_profile(profile)
    profile.save()
    _append_event(profile, HardwareLifecycleEventType.ASSIGNED, actor_id, person=person, site=site, location=location)
    AuditEvent.objects.create(
        tenant=profile.tenant,
        actor_id=actor_id,
        action="asset.hardware.assigned",
        entity_id=asset.entity_id,
        metadata={},
    )
    return _hardware(asset)


@transaction.atomic
def unassign_hardware(*, asset: ClientAsset, actor_id: UUID) -> ClientHardwareAsset:
    profile = _hardware(ClientAsset.objects.select_for_update().get(pk=asset.pk), lock=True)
    if not (profile.assigned_person_id or profile.assigned_site_id or profile.assigned_location_id):
        return profile
    _append_event(
        profile,
        HardwareLifecycleEventType.UNASSIGNED,
        actor_id,
        person=profile.assigned_person,
        site=profile.assigned_site,
        location=profile.assigned_location,
    )
    profile.assigned_person = profile.assigned_site = profile.assigned_location = None
    profile.assigned_at = None
    _validate_profile(profile)
    profile.save()
    AuditEvent.objects.create(
        tenant=profile.tenant,
        actor_id=actor_id,
        action="asset.hardware.unassigned",
        entity_id=asset.entity_id,
        metadata={},
    )
    return _hardware(asset)


@transaction.atomic
def dispose_hardware(  # type: ignore[no-untyped-def]
    *, asset: ClientAsset, actor_id: UUID, disposed_on, method: str, reason: str
) -> ClientHardwareAsset:
    profile = _hardware(ClientAsset.objects.select_for_update().get(pk=asset.pk), lock=True)
    if profile.lifecycle_state == HardwareLifecycleState.DISPOSED:
        raise InventoryError("Hardware is already disposed.")
    old_state = profile.lifecycle_state
    if profile.assigned_person_id or profile.assigned_site_id or profile.assigned_location_id:
        _append_event(
            profile,
            HardwareLifecycleEventType.UNASSIGNED,
            actor_id,
            person=profile.assigned_person,
            site=profile.assigned_site,
            location=profile.assigned_location,
        )
    profile.assigned_person = profile.assigned_site = profile.assigned_location = None
    profile.assigned_at = None
    profile.lifecycle_state = HardwareLifecycleState.DISPOSED
    profile.disposed_on, profile.disposal_method, profile.disposal_reason = disposed_on, method, reason.strip()
    _validate_profile(profile)
    profile.save()
    _append_event(profile, HardwareLifecycleEventType.DISPOSED, actor_id, from_state=old_state)
    AuditEvent.objects.create(
        tenant=profile.tenant,
        actor_id=actor_id,
        action="asset.hardware.disposed",
        entity_id=asset.entity_id,
        metadata={},
    )
    return _hardware(asset)


def vendors_for_scope(scope: DataScope) -> QuerySet[Organization]:
    if scope.organization_id is None:
        return Organization.objects.none()
    return (
        Organization.objects.filter(
            tenant_id=scope.tenant_id,
            supplied_client_assets__organization_id=scope.organization_id,
            supplied_client_assets__archived_at__isnull=True,
        )
        .select_related("entity")
        .prefetch_related("classifications")
        .annotate(asset_count=Count("supplied_client_assets", distinct=True))
        .order_by("entity__display_name", "entity_id")
    )
