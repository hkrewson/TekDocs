"""Git-native template identities; no legacy document or block ownership."""

import uuid

from django.db import models

from .model_support import TimestampedModel
from .scoping import OrganizationScopedManager, TenantScopedManager


class RepositoryTemplate(TimestampedModel):
    objects = models.Manager()
    scoped = TenantScopedManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.PROTECT)
    repository = models.ForeignKey("core.WorkspaceRepository", on_delete=models.PROTECT)
    content_id = models.UUIDField()
    enabled = models.BooleanField(default=True)
    library_visible = models.BooleanField(default=True)
    latest_revision = models.ForeignKey(
        "core.RepositoryTemplateRevision", on_delete=models.PROTECT, null=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["repository", "content_id"], name="native_template_source_unique")
        ]


class RepositoryTemplateRevision(TimestampedModel):
    objects = models.Manager()
    scoped = TenantScopedManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)
    template = models.ForeignKey(RepositoryTemplate, on_delete=models.PROTECT, related_name="revisions")
    commit = models.ForeignKey("core.RepositoryCommit", on_delete=models.PROTECT)
    manifest = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["template", "checksum"], name="native_template_revision_unique")]


class RepositoryTemplateEnrollment(TimestampedModel):
    objects = models.Manager()
    scoped = OrganizationScopedManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT)
    organization = models.ForeignKey("core.Organization", on_delete=models.PROTECT)
    workspace = models.ForeignKey("core.Workspace", on_delete=models.PROTECT)
    repository = models.ForeignKey("core.WorkspaceRepository", on_delete=models.PROTECT)
    content_id = models.UUIDField()
    source_template = models.ForeignKey(RepositoryTemplate, on_delete=models.PROTECT)
    applied_revision = models.ForeignKey(RepositoryTemplateRevision, on_delete=models.PROTECT)
    placement_map = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["repository", "content_id"], name="native_template_enrollment_unique")
        ]
