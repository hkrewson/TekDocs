import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .model_support import TimestampedModel
from .scoping import OrganizationScopedManager, TenantScopedManager


class DocumentTemplateRevision(TimestampedModel):
    """An immutable composition manifest for one MSP-owned reusable template."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="document_template_revisions")
    template = models.ForeignKey("core.Document", on_delete=models.PROTECT, related_name="template_revisions")
    revision_number = models.PositiveIntegerField()
    manifest = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="document_template_revisions",
    )

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        ordering = ("template_id", "revision_number")
        constraints = [
            models.UniqueConstraint(fields=["template", "revision_number"], name="unique_template_revision_number"),
            models.UniqueConstraint(fields=["template", "checksum"], name="unique_template_revision_checksum"),
        ]
        indexes = [models.Index(fields=["tenant", "template", "revision_number"], name="core_tplrev_lookup_idx")]

    def __str__(self) -> str:
        return f"{self.template_id} template revision {self.revision_number}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Template revisions are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Template revisions are append-only")


class DocumentTemplateEnrollment(TimestampedModel):
    """Tracks a client document created from an MSP template and its controlled rollout state."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="document_template_enrollments")
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.PROTECT,
        related_name="document_template_enrollments",
    )
    source_template = models.ForeignKey(
        "core.Document",
        on_delete=models.PROTECT,
        related_name="template_enrollments",
    )
    destination_document = models.OneToOneField(
        "core.Document",
        on_delete=models.PROTECT,
        related_name="template_enrollment",
    )
    applied_revision = models.ForeignKey(
        DocumentTemplateRevision,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    placement_map = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_document_template_enrollments",
    )
    last_applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="applied_document_template_enrollments",
    )
    last_applied_at = models.DateTimeField(default=timezone.now)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        indexes = [
            models.Index(
                fields=["tenant", "organization", "source_template", "archived_at"],
                name="core_tplenroll_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source_template_id} enrolled for {self.organization_id}"

    def clean(self) -> None:
        if self.organization_id and self.organization.tenant_id != self.tenant_id:
            raise ValidationError("Template enrollment organization must belong to its tenant")
        if self.source_template_id and (
            self.source_template.tenant_id != self.tenant_id or self.source_template.organization_id is not None
        ):
            raise ValidationError("Template enrollment source must be an MSP-owned document")
        if self.destination_document_id and (
            self.destination_document.tenant_id != self.tenant_id
            or self.destination_document.organization_id != self.organization_id
        ):
            raise ValidationError("Template enrollment destination must belong to its client organization")
        if self.applied_revision_id and self.applied_revision.template_id != self.source_template_id:
            raise ValidationError("Applied template revision must belong to the source template")


__all__ = ["DocumentTemplateEnrollment", "DocumentTemplateRevision"]
