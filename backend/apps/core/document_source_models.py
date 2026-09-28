import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .model_support import TimestampedModel
from .scoping import OrganizationScopedManager


class DocumentSourceKind(models.TextChoices):
    MARKDOWN = "markdown", "Markdown"
    HTML = "html", "HTML"
    AUTO = "auto", "Automatic"


class DocumentRemoteSource(TimestampedModel):
    """A public HTTPS source monitored for one workspace-owned document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="document_remote_sources")
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.PROTECT,
        related_name="document_remote_sources",
        null=True,
        blank=True,
    )
    document = models.OneToOneField("core.Document", on_delete=models.PROTECT, related_name="remote_source")
    url = models.URLField(max_length=500)
    source_kind = models.CharField(max_length=12, choices=DocumentSourceKind.choices, default=DocumentSourceKind.AUTO)
    enabled = models.BooleanField(default=True)
    check_interval_minutes = models.PositiveIntegerField(default=1440)
    next_check_at = models.DateTimeField(default=timezone.now)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_applied_observation = models.ForeignKey(
        "core.DocumentRemoteObservation",
        on_delete=models.PROTECT,
        related_name="applied_to_sources",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_document_remote_sources",
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        indexes = [
            models.Index(fields=("tenant", "organization", "enabled", "next_check_at"), name="core_docsource_due_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_interval_minutes__gte=15, check_interval_minutes__lte=10080),
                name="document_source_interval_bounded",
            )
        ]

    def __str__(self) -> str:
        return f"Remote source for {self.document_id}"


class DocumentRemoteObservation(models.Model):
    """Immutable, bounded evidence from one remote-source fetch."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="document_remote_observations")
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.PROTECT,
        related_name="document_remote_observations",
        null=True,
        blank=True,
    )
    source = models.ForeignKey(DocumentRemoteSource, on_delete=models.PROTECT, related_name="observations")
    state = models.CharField(
        max_length=16,
        choices=(("unchanged", "Unchanged"), ("changed", "Changed"), ("failed", "Failed")),
    )
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    etag_digest = models.CharField(max_length=64, blank=True)
    last_modified_digest = models.CharField(max_length=64, blank=True)
    content_digest = models.CharField(max_length=64, blank=True)
    canonical_markdown = models.TextField(blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-fetched_at", "id")
        indexes = [models.Index(fields=("source", "fetched_at"), name="core_docobservation_idx")]

    def __str__(self) -> str:
        return f"{self.source_id} observed at {self.fetched_at}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Remote document observations are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Remote document observations are retained")


__all__ = ["DocumentRemoteObservation", "DocumentRemoteSource", "DocumentSourceKind"]
