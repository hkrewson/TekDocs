import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .document_keys import BINDING_NAME_PATTERN
from .model_support import TimestampedModel
from .scoping import OrganizationScopedManager


class DocumentKeyBinding(TimestampedModel):
    """A named binding from a document to the record its key expressions resolve against.

    A document declares bindings such as ``subject``; a key of ``subject.gateway``
    then reads that field from this target. Binding to ``Entity`` rather than to a
    narrower record type is deliberate: every domain record is entity-anchored, so
    one target type gives one authorization path rather than one per domain.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="document_key_bindings")
    workspace = models.ForeignKey("core.Workspace", on_delete=models.PROTECT, related_name="document_key_bindings")
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.PROTECT,
        related_name="document_key_bindings",
        null=True,
        blank=True,
    )
    document = models.ForeignKey("core.Document", on_delete=models.PROTECT, related_name="key_bindings")
    name = models.CharField(max_length=40)
    target_entity = models.ForeignKey(
        "core.Entity",
        on_delete=models.PROTECT,
        related_name="document_key_bindings",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_document_key_bindings",
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("name", "id")
        constraints = [
            # One spelling per binding name, using the key grammar itself rather than a
            # copy of it. The stored key expression is permanent, so a name that cannot
            # appear in a key must never reach the table.
            models.CheckConstraint(
                condition=models.Q(name__regex=BINDING_NAME_PATTERN),
                name="document_key_binding_name_valid",
            ),
            # Uniqueness applies to live bindings only, so a name can be re-declared
            # against a different record after the previous binding is retired.
            models.UniqueConstraint(
                fields=("document", "name"),
                condition=models.Q(archived_at__isnull=True),
                name="document_key_binding_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        # Retained rather than removed: a retired binding is the record of what a
        # document's keys used to resolve against, which is the first question asked
        # when a document's values change meaning.
        raise ValidationError("Document key bindings must be archived")


__all__ = ["DocumentKeyBinding"]
