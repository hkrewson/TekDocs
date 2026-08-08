from __future__ import annotations

from uuid import UUID

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from .models import AuditEvent, Entity, Organization, Person, PersonAssociation, Tenant
from .scoping import DataScope

FILTER_LOOKUPS = {
    "preferred_name": "person__preferred_name__icontains",
    "kind": "kind__icontains",
    "role": "role__icontains",
    "responsibility": "responsibility__icontains",
    "location": "location__icontains",
    "office": "office__icontains",
    "phone": "person__phone__icontains",
    "email": "person__email__icontains",
}
ORDERING_FIELDS = {
    "full_name": "person__entity__display_name",
    "preferred_name": "person__preferred_name",
    "kind": "kind",
    "role": "role",
    "responsibility": "responsibility",
    "location": "location",
    "office": "office",
    "phone": "person__phone",
    "email": "person__email",
}


def people_for_scope(scope: DataScope) -> QuerySet[PersonAssociation]:
    return (
        PersonAssociation.scoped.for_scope(scope)
        .filter(archived_at__isnull=True)
        .select_related("person", "person__entity", "organization", "organization__entity")
    )


def query_people(
    *,
    scope: DataScope,
    q: str,
    filter_field: str,
    filter_value: str,
    ordering: str,
    page: int,
    page_size: int,
) -> tuple[list[PersonAssociation], int, bool]:
    records = people_for_scope(scope)
    if q:
        records = records.filter(
            Q(person__entity__display_name__icontains=q)
            | Q(person__preferred_name__icontains=q)
            | Q(kind__icontains=q)
            | Q(role__icontains=q)
            | Q(responsibility__icontains=q)
            | Q(location__icontains=q)
            | Q(office__icontains=q)
            | Q(person__phone__icontains=q)
            | Q(person__email__icontains=q)
        )
    if filter_field:
        records = records.filter(**{FILTER_LOOKUPS[filter_field]: filter_value})
    descending = ordering.startswith("-")
    field = ordering.removeprefix("-")
    order_by = ORDERING_FIELDS[field]
    if descending:
        order_by = f"-{order_by}"
    records = records.order_by(order_by, "person__entity_id")
    count = records.count()
    offset = (page - 1) * page_size
    selected = list(records[offset : offset + page_size + 1])
    return selected[:page_size], count, len(selected) > page_size


@transaction.atomic
def create_person(
    *,
    tenant: Tenant,
    organization: Organization | None,
    actor_id: UUID,
    full_name: str,
    preferred_name: str,
    kind: str,
    role: str,
    responsibility: str,
    location: str,
    office: str,
    phone: str,
    email: str,
) -> PersonAssociation:
    entity = Entity.objects.create(tenant=tenant, entity_type="person", display_name=full_name)
    person = Person.objects.create(
        tenant=tenant,
        entity=entity,
        preferred_name=preferred_name,
        phone=phone,
        email=email,
    )
    association = PersonAssociation.objects.create(
        tenant=tenant,
        organization=organization,
        person=person,
        kind=kind,
        role=role,
        responsibility=responsibility,
        location=location,
        office=office,
    )
    AuditEvent.objects.create(
        tenant=tenant,
        actor_id=actor_id,
        action="person.created",
        entity_id=entity.id,
        metadata={},
    )
    return association


@transaction.atomic
def update_person(
    *,
    association: PersonAssociation,
    actor_id: UUID,
    full_name: str,
    preferred_name: str,
    kind: str,
    role: str,
    responsibility: str,
    location: str,
    office: str,
    phone: str,
    email: str,
) -> PersonAssociation:
    person = association.person
    person.entity.display_name = full_name
    person.entity.save(update_fields=("display_name", "updated_at"))
    person.preferred_name = preferred_name
    person.phone = phone
    person.email = email
    person.save(update_fields=("preferred_name", "phone", "email", "updated_at"))
    association.kind = kind
    association.role = role
    association.responsibility = responsibility
    association.location = location
    association.office = office
    association.save(
        update_fields=("kind", "role", "responsibility", "location", "office", "updated_at")
    )
    AuditEvent.objects.create(
        tenant=association.tenant,
        actor_id=actor_id,
        action="person.updated",
        entity_id=person.entity_id,
        metadata={},
    )
    return association


@transaction.atomic
def archive_person_association(*, association: PersonAssociation, actor_id: UUID) -> None:
    association.archived_at = timezone.now()
    association.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=association.tenant,
        actor_id=actor_id,
        action="person.association_archived",
        entity_id=association.person.entity_id,
        metadata={},
    )
