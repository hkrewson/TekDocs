from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.models import AuditEvent, Organization

from .models import AccessCollection, AccessCollectionOrganization, User
from .policy import InstallationMemberContext, PermissionKey, require_permission


def access_collections_for_context(context: InstallationMemberContext) -> QuerySet[AccessCollection]:
    return (
        AccessCollection.scoped.for_tenant(context.tenant)
        .annotate(assignment_count=Count("scoped_role_assignments"))
        .prefetch_related(
            Prefetch(
                "organization_edges",
                queryset=AccessCollectionOrganization.scoped.for_tenant(context.tenant)
                .select_related("organization__entity")
                .order_by("organization__entity__display_name", "organization_id"),
            )
        )
        .order_by("archived_at", "name_key", "id")
    )


def _organizations_for_ids(
    context: InstallationMemberContext,
    organization_entity_ids: list[UUID],
) -> list[Organization]:
    if len(organization_entity_ids) != len(set(organization_entity_ids)):
        raise ValidationError({"organization_ids": "Select each organization at most once."})
    organizations = list(
        Organization.scoped.for_tenant(context.tenant)
        .filter(entity_id__in=organization_entity_ids, entity__archived_at__isnull=True)
        .select_related("entity")
    )
    if len(organizations) != len(organization_entity_ids):
        raise NotFound("One or more organizations are not available.")
    return organizations


def _active_collection_for_update(
    context: InstallationMemberContext,
    collection_id: UUID,
) -> AccessCollection:
    try:
        return AccessCollection.scoped.for_tenant(context.tenant).select_for_update().get(
            pk=collection_id,
            archived_at__isnull=True,
        )
    except AccessCollection.DoesNotExist as exc:
        raise NotFound("The access collection is not available.") from exc


def _replace_organizations(
    *,
    actor: User,
    context: InstallationMemberContext,
    collection: AccessCollection,
    organizations: list[Organization],
) -> None:
    selected = {organization.id: organization for organization in organizations}
    existing = {
        edge.organization_id: edge
        for edge in AccessCollectionOrganization.scoped.for_tenant(context.tenant).filter(collection=collection)
    }
    remove_ids = set(existing) - set(selected)
    if remove_ids:
        AccessCollectionOrganization.scoped.for_tenant(context.tenant).filter(
            collection=collection,
            organization_id__in=remove_ids,
        ).delete()
    AccessCollectionOrganization.objects.bulk_create(
        [
            AccessCollectionOrganization(
                tenant=context.tenant,
                collection=collection,
                organization=organization,
                created_by=actor,
            )
            for organization_id, organization in selected.items()
            if organization_id not in existing
        ]
    )


@transaction.atomic
def create_access_collection(
    *,
    actor: User,
    name: str,
    description: str,
    organization_entity_ids: list[UUID],
) -> AccessCollection:
    context = require_permission(actor, PermissionKey.ACCESS_COLLECTIONS_MANAGE)
    name = " ".join(name.split())
    if not name:
        raise ValidationError({"name": "Enter an access collection name."})
    organizations = _organizations_for_ids(context, organization_entity_ids)
    collection = AccessCollection(
        tenant=context.tenant,
        name=name,
        description=description,
        created_by=actor,
    )
    collection.full_clean(exclude=("name_key",))
    try:
        collection.save()
    except IntegrityError as exc:
        raise ValidationError({"name": "An access collection with this name already exists."}) from exc
    _replace_organizations(
        actor=actor,
        context=context,
        collection=collection,
        organizations=organizations,
    )
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=actor,
        action="access_collection.created",
        entity_id=collection.id,
        metadata={},
    )
    return access_collections_for_context(context).get(pk=collection.pk)


@transaction.atomic
def update_access_collection(
    *,
    actor: User,
    collection_id: UUID,
    name: str,
    description: str,
    organization_entity_ids: list[UUID],
) -> AccessCollection:
    context = require_permission(actor, PermissionKey.ACCESS_COLLECTIONS_MANAGE)
    name = " ".join(name.split())
    if not name:
        raise ValidationError({"name": "Enter an access collection name."})
    organizations = _organizations_for_ids(context, organization_entity_ids)
    collection = _active_collection_for_update(context, collection_id)
    collection.name = name
    collection.description = description
    collection.full_clean(exclude=("name_key",))
    try:
        collection.save(update_fields=("name", "name_key", "description", "updated_at"))
    except IntegrityError as exc:
        raise ValidationError({"name": "An access collection with this name already exists."}) from exc
    _replace_organizations(
        actor=actor,
        context=context,
        collection=collection,
        organizations=organizations,
    )
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=actor,
        action="access_collection.updated",
        entity_id=collection.id,
        metadata={},
    )
    return access_collections_for_context(context).get(pk=collection.pk)


@transaction.atomic
def archive_access_collection(*, actor: User, collection_id: UUID) -> AccessCollection:
    context = require_permission(actor, PermissionKey.ACCESS_COLLECTIONS_MANAGE)
    collection = _active_collection_for_update(context, collection_id)
    collection.archived_at = timezone.now()
    collection.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=context.tenant,
        actor=actor,
        action="access_collection.archived",
        entity_id=collection.id,
        metadata={},
    )
    return access_collections_for_context(context).get(pk=collection.pk)
