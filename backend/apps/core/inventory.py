from __future__ import annotations

import hashlib
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q, QuerySet

from .models import (
    AuditEvent,
    CatalogModel,
    CatalogModelRevision,
    CatalogProduct,
    CatalogProductDocument,
    ClientAsset,
    ClientAssetDocumentProvenance,
    DocumentPublication,
    DocumentPublicationArtifact,
    Entity,
    EntityVisibility,
    Organization,
    PublicationAudience,
    Tenant,
)
from .publications import canonical_json, verify_publication
from .scoping import DataScope


class InventoryError(Exception):
    pass


def require_client(organization: Organization) -> None:
    classifications = {item.kind for item in organization.classifications.all()}
    if "client" not in classifications:
        raise InventoryError("Client assets require a client organization workspace.")


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
        )
        .prefetch_related(_document_prefetch())
    )


def model_choices_for_client(scope: DataScope, *, query: str = "") -> QuerySet[CatalogModel]:
    if scope.organization_id is None:
        return CatalogModel.objects.none()
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
    organization: Organization,
    actor_id: UUID,
    model_entity_id: UUID,
    name: str,
) -> ClientAsset:
    require_client(organization)
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
    entity = Entity.objects.create(
        tenant=tenant,
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
    return assets_for_scope(DataScope.organization(tenant, organization)).get(pk=asset.pk)


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
