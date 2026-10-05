"""Disposable projections of canonical repository-backed Markdown content."""

from __future__ import annotations

import uuid

from django.db import models

from .model_support import TimestampedModel
from .scoping import OrganizationScopedManager


class ContentNodeKind(models.TextChoices):
    DOCUMENT = "document", "Document"
    FRAGMENT = "fragment", "Fragment"


class ContentIndexStatus(models.TextChoices):
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"


class ContentNode(TimestampedModel):
    """One parsed document or reusable fragment at a repository's indexed head."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="content_nodes")
    organization = models.ForeignKey(
        "core.Organization", on_delete=models.CASCADE, related_name="content_nodes", null=True, blank=True
    )
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="content_nodes")
    repository = models.ForeignKey("core.WorkspaceRepository", on_delete=models.CASCADE, related_name="content_nodes")
    indexed_commit = models.ForeignKey("core.RepositoryCommit", on_delete=models.CASCADE, related_name="content_nodes")
    content_id = models.UUIDField()
    source_path = models.CharField(max_length=512)
    kind = models.CharField(max_length=16, choices=ContentNodeKind.choices)
    title = models.CharField(max_length=240)
    markdown = models.TextField()
    frontmatter = models.JSONField(default=dict)
    taxonomy_keys = models.JSONField(default=dict)
    topic_type = models.CharField(max_length=32, blank=True)
    topic_schema_version = models.PositiveSmallIntegerField(null=True, blank=True)
    content_digest = models.CharField(max_length=64)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("source_path", "content_id")
        constraints = [
            models.UniqueConstraint(fields=("repository", "content_id"), name="content_node_identity_unique"),
            models.UniqueConstraint(fields=("repository", "source_path"), name="content_node_path_unique"),
            models.CheckConstraint(condition=models.Q(kind__in=ContentNodeKind.values), name="content_node_kind_valid"),
            models.CheckConstraint(
                condition=models.Q(content_digest__regex=r"^[0-9a-f]{64}$"), name="content_node_digest_valid"
            ),
        ]
        indexes = [
            models.Index(fields=("workspace", "kind", "source_path"), name="core_contentnode_scope_idx"),
        ]


class ContentProperty(models.Model):
    """One normalized portable frontmatter property for a content node."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="content_properties")
    organization = models.ForeignKey(
        "core.Organization", on_delete=models.CASCADE, related_name="content_properties", null=True, blank=True
    )
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="content_properties")
    node = models.ForeignKey(ContentNode, on_delete=models.CASCADE, related_name="properties")
    key = models.CharField(max_length=80)
    value = models.JSONField()

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("key", "id")
        constraints = [
            models.UniqueConstraint(fields=("node", "key"), name="content_property_key_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.node_id}:{self.key}"


class ContentLink(models.Model):
    """One bounded wikilink; reverse relations are the backlink projection."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="content_links")
    organization = models.ForeignKey(
        "core.Organization", on_delete=models.CASCADE, related_name="content_links", null=True, blank=True
    )
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="content_links")
    source = models.ForeignKey(ContentNode, on_delete=models.CASCADE, related_name="outgoing_links")
    target = models.ForeignKey(ContentNode, on_delete=models.CASCADE, related_name="backlinks", null=True, blank=True)
    target_content_id = models.UUIDField()
    fragment = models.CharField(max_length=120, blank=True)
    label = models.CharField(max_length=240, blank=True)
    ordinal = models.PositiveIntegerField()

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("source_id", "ordinal", "id")
        constraints = [
            models.UniqueConstraint(fields=("source", "ordinal"), name="content_link_ordinal_unique"),
        ]
        indexes = [models.Index(fields=("workspace", "target_content_id"), name="core_contentlink_target_idx")]

    def __str__(self) -> str:
        return f"{self.source_id}:{self.ordinal}"


class ContentFinding(models.Model):
    """Sanitized parser, link, taxonomy, or publication-preflight diagnostic."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="content_findings")
    organization = models.ForeignKey(
        "core.Organization", on_delete=models.CASCADE, related_name="content_findings", null=True, blank=True
    )
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="content_findings")
    node = models.ForeignKey(ContentNode, on_delete=models.CASCADE, related_name="findings")
    code = models.CharField(max_length=80)
    severity = models.CharField(max_length=16)
    detail = models.JSONField(default=dict)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("node_id", "code", "id")

    def __str__(self) -> str:
        return f"{self.node_id}:{self.code}"


class ContentIndexAttempt(models.Model):
    """Retained result for an accepted or rejected projection attempt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="content_index_attempts")
    organization = models.ForeignKey(
        "core.Organization", on_delete=models.CASCADE, related_name="content_index_attempts", null=True, blank=True
    )
    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE, related_name="content_index_attempts")
    repository = models.ForeignKey(
        "core.WorkspaceRepository", on_delete=models.CASCADE, related_name="content_index_attempts"
    )
    commit = models.ForeignKey("core.RepositoryCommit", on_delete=models.CASCADE, related_name="content_index_attempts")
    status = models.CharField(max_length=16, choices=ContentIndexStatus.choices)
    diagnostics = models.JSONField(default=list)
    projection_digest = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.UniqueConstraint(fields=("repository", "commit"), name="content_index_attempt_unique"),
            models.CheckConstraint(
                condition=models.Q(status__in=ContentIndexStatus.values), name="content_index_status_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository_id}:{self.commit_id}:{self.status}"
