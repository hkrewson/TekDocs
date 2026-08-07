import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Tenant(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class InstallationState(models.Model):
    """The single, migration-created installation bootstrap record."""

    SINGLETON_ID = 1

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_ID, editable=False)
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.PROTECT,
        related_name="installation_state",
        null=True,
        blank=True,
    )
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_installation",
        null=True,
        blank=True,
    )
    bootstrapped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="installation_state_singleton"),
            models.CheckConstraint(
                condition=(
                    models.Q(tenant__isnull=True, owner__isnull=True, bootstrapped_at__isnull=True)
                    | models.Q(tenant__isnull=False, owner__isnull=False, bootstrapped_at__isnull=False)
                ),
                name="installation_state_complete_or_empty",
            ),
        ]

    def __str__(self) -> str:
        return "TekDocs installation state"

    @property
    def is_bootstrapped(self) -> bool:
        return self.bootstrapped_at is not None

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Installation state cannot be deleted")


class Entity(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="entities")
    entity_type = models.CharField(max_length=80)
    display_name = models.CharField(max_length=240)
    custom_fields = models.JSONField(default=dict, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "entity_type"]),
            models.Index(fields=["tenant", "display_name"]),
        ]

    def __str__(self) -> str:
        return self.display_name


class EntityLink(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="entity_links")
    source = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="outgoing_links")
    target = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="incoming_links")
    link_type = models.CharField(max_length=80)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "target", "link_type"], name="unique_typed_entity_link"),
            models.CheckConstraint(condition=~models.Q(source=models.F("target")), name="entity_link_not_self"),
        ]
        indexes = [models.Index(fields=["tenant", "link_type"])]

    def __str__(self) -> str:
        return f"{self.source_id} {self.link_type} {self.target_id}"

    def clean(self) -> None:
        if self.source_id and self.tenant_id != self.source.tenant_id:
            raise ValidationError("Source entity must belong to the link tenant")
        if self.target_id and self.tenant_id != self.target.tenant_id:
            raise ValidationError("Target entity must belong to the link tenant")

class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="audit_events", null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=120)
    entity_id = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-occurred_at",)
        indexes = [models.Index(fields=["tenant", "action", "occurred_at"])]

    def __str__(self) -> str:
        return f"{self.action} at {self.occurred_at}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Audit events are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Audit events are append-only")
