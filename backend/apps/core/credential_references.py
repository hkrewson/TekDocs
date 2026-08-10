from __future__ import annotations

import re
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from .models import (
    AuditEvent,
    CredentialReference,
    CredentialReferenceProvider,
    Entity,
    EntityVisibility,
    Organization,
    Tenant,
)
from .scoping import DataScope

_ONEPASSWORD_ID = re.compile(r"^[a-z0-9]{26}$")
_ONEPASSWORD_ACCOUNT_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+1password\.(?:com|ca|eu)$")


class CredentialReferenceProviderAdapter(Protocol):
    def normalize(self, value: str) -> str: ...


class OnePasswordPrivateLinkAdapter:
    """Validate the non-secret Copy Private Link form without contacting 1Password."""

    def normalize(self, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValidationError("Enter a valid 1Password Private Link.")
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as exc:
            raise ValidationError("Enter a valid 1Password Private Link.") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname != "start.1password.com"
            or port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/open/i"
            or parsed.fragment
        ):
            raise ValidationError("Use a 1Password Copy Private Link, not a share link or arbitrary URL.")
        try:
            query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
        except ValueError as exc:
            raise ValidationError("The 1Password Private Link query is invalid.") from exc
        if set(query) != {"a", "v", "i", "h"} or any(len(values) != 1 for values in query.values()):
            raise ValidationError("The 1Password Private Link has an invalid parameter set.")
        account_id, vault_id, item_id = (query[key][0] for key in ("a", "v", "i"))
        if not all(_ONEPASSWORD_ID.fullmatch(value) for value in (account_id, vault_id, item_id)):
            raise ValidationError("The 1Password Private Link contains an invalid identifier.")
        account_host = query["h"][0].lower()
        if not _ONEPASSWORD_ACCOUNT_HOST.fullmatch(account_host):
            raise ValidationError("The 1Password Private Link contains an invalid account host.")
        canonical = urlunsplit(
            (
                "https",
                "start.1password.com",
                "/open/i",
                urlencode({"a": account_id, "v": vault_id, "i": item_id, "h": account_host}),
                "",
            )
        )
        if value != canonical:
            raise ValidationError("Use the unmodified link produced by 1Password Copy Private Link.")
        return canonical


PROVIDERS: dict[str, CredentialReferenceProviderAdapter] = {
    CredentialReferenceProvider.ONEPASSWORD: OnePasswordPrivateLinkAdapter(),
}


def normalize_credential_reference(provider: str, value: str) -> str:
    adapter = PROVIDERS.get(provider)
    if adapter is None:
        raise ValidationError("This credential-reference provider is not supported.")
    return adapter.normalize(value)


def references_for_scope(scope: DataScope) -> QuerySet[CredentialReference]:
    return (
        CredentialReference.scoped.for_scope(scope)
        .filter(archived_at__isnull=True, entity__archived_at__isnull=True)
        .select_related("entity", "organization")
    )


def query_references(*, scope: DataScope, q: str) -> QuerySet[CredentialReference]:
    records = references_for_scope(scope)
    if q:
        records = records.filter(Q(entity__display_name__icontains=q))
    return records.order_by("entity__display_name", "entity_id")


@transaction.atomic
def create_credential_reference(
    *, tenant: Tenant, organization: Organization | None, actor_id: UUID, title: str, provider: str, reference_url: str
) -> CredentialReference:
    canonical_url = normalize_credential_reference(provider, reference_url)
    entity = Entity.objects.create(
        tenant=tenant,
        organization=organization,
        entity_type="credential_reference",
        display_name=title,
        visibility=EntityVisibility.MSP_PRIVATE,
    )
    reference = CredentialReference.objects.create(
        tenant=tenant,
        organization=organization,
        entity=entity,
        provider=provider,
        reference_url=canonical_url,
    )
    AuditEvent.objects.create(
        tenant=tenant, actor_id=actor_id, action="credential_reference.created", entity_id=entity.id, metadata={}
    )
    return reference


@transaction.atomic
def update_credential_reference(
    *, reference: CredentialReference, actor_id: UUID, title: str | None = None, reference_url: str | None = None
) -> CredentialReference:
    if title is not None:
        reference.entity.display_name = title
        reference.entity.save(update_fields=("display_name", "updated_at"))
    if reference_url is not None:
        reference.reference_url = normalize_credential_reference(reference.provider, reference_url)
        reference.save(update_fields=("reference_url", "updated_at"))
    AuditEvent.objects.create(
        tenant=reference.tenant,
        actor_id=actor_id,
        action="credential_reference.updated",
        entity_id=reference.entity_id,
        metadata={},
    )
    return reference


@transaction.atomic
def archive_credential_reference(*, reference: CredentialReference, actor_id: UUID) -> None:
    archived_at = timezone.now()
    reference.archived_at = archived_at
    reference.save(update_fields=("archived_at", "updated_at"))
    reference.entity.archived_at = archived_at
    reference.entity.save(update_fields=("archived_at", "updated_at"))
    AuditEvent.objects.create(
        tenant=reference.tenant,
        actor_id=actor_id,
        action="credential_reference.archived",
        entity_id=reference.entity_id,
        metadata={},
    )


def record_credential_reference_open(*, reference: CredentialReference, actor_id: UUID) -> str:
    canonical_url = normalize_credential_reference(reference.provider, reference.reference_url)
    AuditEvent.objects.create(
        tenant=reference.tenant,
        actor_id=actor_id,
        action="credential_reference.opened",
        entity_id=reference.entity_id,
        metadata={},
    )
    return canonical_url
