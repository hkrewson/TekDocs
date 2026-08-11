import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from .scoping import OrganizationScopedManager, TenantScopedManager

WORKSPACE_UUID_NAMESPACE = uuid.UUID("6890dc87-8d91-4f76-a6eb-99dfd06904a5")


def workspace_identity_uuid(*, tenant_id: uuid.UUID, organization_id: uuid.UUID | None) -> uuid.UUID:
    owner = "msp" if organization_id is None else f"organization:{organization_id}"
    return uuid.uuid5(WORKSPACE_UUID_NAMESPACE, f"tenant:{tenant_id}:{owner}")


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

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        creating = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creating:
                Workspace.objects.get_or_create(
                    id=workspace_identity_uuid(tenant_id=self.id, organization_id=None),
                    tenant=self,
                    kind=WorkspaceKind.MSP,
                    organization=None,
                )


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


class EntityVisibility(models.TextChoices):
    MSP_PRIVATE = "msp_private", "MSP private"
    CLIENT_VISIBLE = "client_visible", "Client visible"


class CredentialReferenceProvider(models.TextChoices):
    ONEPASSWORD = "onepassword", "1Password"


class WorkspaceKind(models.TextChoices):
    MSP = "msp", "MSP"
    ORGANIZATION = "organization", "Organization"


class Workspace(TimestampedModel):
    """Stable, explicit owner identity for one MSP or organization workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="workspaces")
    kind = models.CharField(max_length=20, choices=WorkspaceKind.choices)
    organization = models.OneToOneField(
        "Organization",
        on_delete=models.PROTECT,
        related_name="ownership_workspace",
        null=True,
        blank=True,
    )

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind=WorkspaceKind.MSP, organization__isnull=True)
                    | models.Q(kind=WorkspaceKind.ORGANIZATION, organization__isnull=False)
                ),
                name="workspace_kind_owner_shape",
            ),
            models.UniqueConstraint(
                fields=("tenant",),
                condition=models.Q(kind=WorkspaceKind.MSP),
                name="one_msp_workspace_per_tenant",
            ),
        ]
        indexes = [models.Index(fields=("tenant", "kind"), name="core_workspace_tenant_kind_idx")]

    def __str__(self) -> str:
        if self.organization_id:
            return f"{self.tenant}: {self.organization}"
        return f"{self.tenant}: MSP"

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if not self._state.adding:
            previous = Workspace.objects.only("tenant_id", "kind", "organization_id").get(pk=self.pk)
            if (
                previous.tenant_id != self.tenant_id
                or previous.kind != self.kind
                or previous.organization_id != self.organization_id
            ):
                raise ValidationError("Workspace ownership identity is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Workspace ownership identities cannot be deleted")

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if organization is not None and organization.tenant_id != self.tenant_id:
            raise ValidationError("Workspace organization must belong to its tenant")


def workspace_for_owner(*, tenant: Tenant, organization: "Organization | None") -> Workspace:
    if organization is None:
        return Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.MSP, organization__isnull=True)
    if organization.tenant_id != tenant.id:
        raise ValidationError("Workspace organization must belong to its tenant")
    return Workspace.objects.get(tenant=tenant, kind=WorkspaceKind.ORGANIZATION, organization=organization)


class EntityManager(models.Manager["Entity"]):
    def create_owned(self, **kwargs):  # type: ignore[no-untyped-def]
        """Create an entity only after resolving its explicit owner scope."""

        tenant = kwargs.get("tenant")
        organization = kwargs.get("organization")
        if tenant is None:
            raise ValidationError("Entity creation requires an explicit tenant")
        kwargs["workspace"] = workspace_for_owner(tenant=tenant, organization=organization)
        return self.create(**kwargs)


class Entity(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="entities")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="entities")
    entity_type = models.CharField(max_length=80)
    display_name = models.CharField(max_length=240)
    custom_fields = models.JSONField(default=dict, blank=True)
    visibility = models.CharField(
        max_length=24,
        choices=EntityVisibility.choices,
        default=EntityVisibility.MSP_PRIVATE,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="scoped_entities",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = EntityManager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(visibility__in=EntityVisibility.values),
                name="entity_visibility_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "entity_type"]),
            models.Index(fields=["tenant", "display_name"]),
            models.Index(fields=["tenant", "organization", "entity_type"]),
            models.Index(fields=["tenant", "organization", "visibility"]),
        ]

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if not self._state.adding:
            previous = Entity.objects.only("tenant_id", "workspace_id", "organization_id").get(pk=self.pk)
            if (
                previous.tenant_id != self.tenant_id
                or previous.workspace_id != self.workspace_id
                or previous.organization_id != self.organization_id
            ):
                raise ValidationError("Entity ownership identity is immutable")
        super().save(*args, **kwargs)

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if self.workspace_id and (
            self.workspace.tenant_id != self.tenant_id or self.workspace.organization_id != self.organization_id
        ):
            raise ValidationError("Entity workspace must match its tenant and organization scope")
        if organization is not None and self.tenant_id != organization.tenant_id:
            raise ValidationError("Organization scope must belong to the entity tenant")


class CredentialReference(TimestampedModel):
    """A scoped pointer to a credential held and revealed by an external provider."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="credential_references")
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="credential_references",
        null=True,
        blank=True,
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="credential_reference")
    provider = models.CharField(max_length=32, choices=CredentialReferenceProvider.choices)
    reference_url = models.CharField(max_length=1000)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(provider__in=CredentialReferenceProvider.values),
                name="credential_reference_provider_valid",
            )
        ]
        indexes = [models.Index(fields=("tenant", "organization", "archived_at"), name="core_credref_scope_idx")]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Credential reference and entity scopes must match")
        if organization is not None and organization.tenant_id != self.tenant_id:
            raise ValidationError("Credential reference organization must belong to its tenant")


class CatalogProductKind(models.TextChoices):
    HARDWARE = "hardware", "Hardware"
    SOFTWARE = "software", "Software"


class CatalogModelLifecycle(models.TextChoices):
    ACTIVE = "active", "Active"
    DISCONTINUED = "discontinued", "Discontinued"
    PRE_RELEASE = "pre_release", "Pre-release"


class CatalogProduct(TimestampedModel):
    """A supplier-owned, addressable hardware or software product family."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_products")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="catalog_products")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="catalog_product")
    kind = models.CharField(max_length=16, choices=CatalogProductKind.choices)
    description = models.CharField(max_length=1000, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        indexes = [
            models.Index(fields=("tenant", "organization", "kind", "archived_at"), name="core_catprod_scope_idx")
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog product and entity scopes must match")
        if self.organization_id and self.organization.tenant_id != self.tenant_id:
            raise ValidationError("Catalog product organization must belong to its tenant")


class CatalogSpecificationDefinition(TimestampedModel):
    """Stable supplier-owned identity for an immutable specification schema history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_specification_definitions")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="catalog_specification_definitions"
    )
    name = models.CharField(max_length=160)
    product_kind = models.CharField(max_length=16, choices=CatalogProductKind.choices)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "organization", "product_kind", "name"),
                name="unique_catalog_spec_definition_name",
            )
        ]
        indexes = [
            models.Index(
                fields=("tenant", "organization", "product_kind", "archived_at"),
                name="core_catspecdef_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding and "archived_at" not in (kwargs.get("update_fields") or ()):
            raise ValidationError("Specification-definition identity is immutable")
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.organization_id and self.organization.tenant_id != self.tenant_id:
            raise ValidationError("Specification definition organization must belong to its tenant")


class CatalogSpecificationDefinitionVersion(models.Model):
    """An immutable JSON Schema contract used by catalog-model revisions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_specification_versions")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="catalog_specification_versions"
    )
    definition = models.ForeignKey(CatalogSpecificationDefinition, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    schema = models.JSONField()
    checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="catalog_specification_versions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("definition_id", "version")
        constraints = [
            models.UniqueConstraint(fields=("definition", "version"), name="unique_catalog_spec_definition_version"),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="catalog_spec_version_positive"),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "definition", "version"), name="core_catspecver_scope_idx")
        ]

    def __str__(self) -> str:
        return f"{self.definition_id} v{self.version}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Specification-definition versions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Specification-definition versions are immutable")

    def clean(self) -> None:
        if self.definition_id and (
            self.definition.tenant_id != self.tenant_id or self.definition.organization_id != self.organization_id
        ):
            raise ValidationError("Specification version and definition scopes must match")


class CatalogModel(TimestampedModel):
    """A stable, addressable supplier template whose data changes through revisions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_models")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="catalog_models")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="catalog_model")
    product = models.ForeignKey(CatalogProduct, on_delete=models.PROTECT, related_name="models")
    model_number = models.CharField(max_length=160)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "organization", "product", "model_number"),
                name="unique_catalog_model_number",
            )
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "product", "archived_at"), name="core_catmodel_scope_idx")
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog model and entity scopes must match")
        if self.product_id and (
            self.product.tenant_id != self.tenant_id or self.product.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog model and product scopes must match")


class CatalogModelRevision(models.Model):
    """Immutable model specifications pinned to one immutable schema version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_model_revisions")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="catalog_model_revisions")
    model = models.ForeignKey(CatalogModel, on_delete=models.PROTECT, related_name="revisions")
    parent = models.OneToOneField(
        "self", on_delete=models.PROTECT, related_name="child_revision", null=True, blank=True
    )
    revision = models.PositiveIntegerField()
    specification_version = models.ForeignKey(
        CatalogSpecificationDefinitionVersion,
        on_delete=models.PROTECT,
        related_name="model_revisions",
    )
    lifecycle = models.CharField(max_length=24, choices=CatalogModelLifecycle.choices)
    specifications = models.JSONField(default=dict)
    notes = models.CharField(max_length=1000, blank=True)
    checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="catalog_model_revisions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("model_id", "revision")
        constraints = [
            models.UniqueConstraint(fields=("model", "revision"), name="unique_catalog_model_revision"),
            models.CheckConstraint(condition=models.Q(revision__gte=1), name="catalog_model_revision_positive"),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "model", "revision"), name="core_catmodelrev_scope_idx")
        ]

    def __str__(self) -> str:
        return f"{self.model_id} r{self.revision}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Catalog model revisions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Catalog model revisions are immutable")

    def clean(self) -> None:
        if self.model_id and (
            self.model.tenant_id != self.tenant_id or self.model.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog model revision and model scopes must match")
        if self.specification_version_id and (
            self.specification_version.tenant_id != self.tenant_id
            or self.specification_version.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog model revision and specification scopes must match")


class CatalogProductDocument(TimestampedModel):
    """A supplier-owned association to one exact client-visible STATIC publication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="catalog_product_documents")
    organization = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="catalog_product_documents")
    product = models.ForeignKey(CatalogProduct, on_delete=models.PROTECT, related_name="document_associations")
    model = models.ForeignKey(
        CatalogModel,
        on_delete=models.PROTECT,
        related_name="document_associations",
        null=True,
        blank=True,
    )
    publication = models.ForeignKey(
        "DocumentPublication", on_delete=models.PROTECT, related_name="catalog_associations"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="catalog_product_documents",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("publication__title", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("product", "publication"),
                condition=models.Q(archived_at__isnull=True, model__isnull=True),
                name="unique_active_product_document",
            ),
            models.UniqueConstraint(
                fields=("product", "model", "publication"),
                condition=models.Q(archived_at__isnull=True, model__isnull=False),
                name="unique_active_model_document",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant", "organization", "product", "model", "archived_at"),
                name="core_catdoc_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product_id}: {self.publication_id}"

    def clean(self) -> None:
        if self.product_id and (
            self.product.tenant_id != self.tenant_id or self.product.organization_id != self.organization_id
        ):
            raise ValidationError("Catalog document and product scopes must match")
        model = self.model if self.model_id else None
        if model is not None and (
            model.tenant_id != self.tenant_id
            or model.organization_id != self.organization_id
            or model.product_id != self.product_id
        ):
            raise ValidationError("Catalog document model must belong to its product and supplier")
        if self.publication_id and (
            self.publication.tenant_id != self.tenant_id
            or self.publication.organization_id != self.organization_id
            or self.publication.audience != PublicationAudience.CLIENT_VISIBLE
        ):
            raise ValidationError("Catalog documentation requires a client-visible supplier publication")


class ClientAsset(TimestampedModel):
    """A client-owned asset retaining the exact supplier model provenance present at creation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="client_assets")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="client_assets", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="client_asset")
    supplier = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="supplied_client_assets")
    product = models.ForeignKey(CatalogProduct, on_delete=models.PROTECT, related_name="client_assets")
    model = models.ForeignKey(CatalogModel, on_delete=models.PROTECT, related_name="client_assets")
    model_revision = models.ForeignKey(CatalogModelRevision, on_delete=models.PROTECT, related_name="client_assets")
    specification_version = models.ForeignKey(
        CatalogSpecificationDefinitionVersion,
        on_delete=models.PROTECT,
        related_name="client_assets",
    )
    specifications = models.JSONField(default=dict)
    provenance_checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_client_assets",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        indexes = [
            models.Index(fields=("tenant", "organization", "archived_at"), name="core_asset_scope_idx"),
            models.Index(fields=("tenant", "organization", "supplier"), name="core_asset_supplier_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Client asset and entity scopes must match")
        organization = self.organization if self.organization_id else None
        if organization is not None and organization.tenant_id != self.tenant_id:
            raise ValidationError("Client asset organization must belong to its tenant")
        if self.supplier_id and self.supplier.tenant_id != self.tenant_id:
            raise ValidationError("Client asset supplier must belong to its tenant")
        if self.product_id and (
            self.product.tenant_id != self.tenant_id or self.product.organization_id != self.supplier_id
        ):
            raise ValidationError("Client asset product must belong to its retained supplier")
        if self.model_id and (
            self.model.tenant_id != self.tenant_id
            or self.model.organization_id != self.supplier_id
            or self.model.product_id != self.product_id
        ):
            raise ValidationError("Client asset model must belong to its retained product")
        if self.model_revision_id and (
            self.model_revision.tenant_id != self.tenant_id
            or self.model_revision.organization_id != self.supplier_id
            or self.model_revision.model_id != self.model_id
        ):
            raise ValidationError("Client asset revision must belong to its retained model")
        if self.specification_version_id and (
            self.specification_version_id != self.model_revision.specification_version_id
        ):
            raise ValidationError("Client asset specification version must match its retained model revision")


class HardwareLifecycleState(models.TextChoices):
    IN_STOCK = "in_stock", "In stock"
    IN_SERVICE = "in_service", "In service"
    REPAIR = "repair", "Repair"
    RETIRED = "retired", "Retired"
    DISPOSED = "disposed", "Disposed"


class HardwareAcquisitionMethod(models.TextChoices):
    PURCHASE = "purchase", "Purchase"
    LEASE = "lease", "Lease"
    RENTAL = "rental", "Rental"
    TRANSFER = "transfer", "Transfer"
    DONATION = "donation", "Donation"
    OTHER = "other", "Other"


class HardwareDisposalMethod(models.TextChoices):
    RECYCLED = "recycled", "Recycled"
    RETURNED = "returned", "Returned"
    SOLD = "sold", "Sold"
    DONATED = "donated", "Donated"
    DESTROYED = "destroyed", "Destroyed"
    LOST = "lost", "Lost"
    OTHER = "other", "Other"


class ClientHardwareAsset(TimestampedModel):
    """Mutable current-state projection for one client-owned hardware asset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="client_hardware_assets")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="client_hardware_assets", null=True, blank=True
    )
    asset = models.OneToOneField(ClientAsset, on_delete=models.PROTECT, related_name="hardware")
    serial_number = models.CharField(max_length=160, blank=True)
    asset_tag = models.CharField(max_length=120, blank=True)
    lifecycle_state = models.CharField(
        max_length=24, choices=HardwareLifecycleState.choices, default=HardwareLifecycleState.IN_STOCK
    )
    acquired_on = models.DateField(null=True, blank=True)
    acquisition_method = models.CharField(max_length=24, choices=HardwareAcquisitionMethod.choices, blank=True)
    acquisition_reference = models.CharField(max_length=240, blank=True)
    warranty_provider = models.CharField(max_length=160, blank=True)
    warranty_starts_on = models.DateField(null=True, blank=True)
    warranty_ends_on = models.DateField(null=True, blank=True)
    warranty_reference = models.CharField(max_length=240, blank=True)
    assigned_person = models.ForeignKey(
        "PersonAssociation", on_delete=models.PROTECT, related_name="assigned_hardware", null=True, blank=True
    )
    assigned_site = models.ForeignKey(
        "Site", on_delete=models.PROTECT, related_name="assigned_hardware", null=True, blank=True
    )
    assigned_location = models.ForeignKey(
        "Location", on_delete=models.PROTECT, related_name="assigned_hardware", null=True, blank=True
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    disposed_on = models.DateField(null=True, blank=True)
    disposal_method = models.CharField(max_length=24, choices=HardwareDisposalMethod.choices, blank=True)
    disposal_reason = models.CharField(max_length=500, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(lifecycle_state__in=HardwareLifecycleState.values),
                name="hardware_state_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(acquisition_method="")
                | models.Q(acquisition_method__in=HardwareAcquisitionMethod.values),
                name="hardware_acquisition_method_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(disposal_method="") | models.Q(disposal_method__in=HardwareDisposalMethod.values),
                name="hardware_disposal_method_valid",
            ),
            models.UniqueConstraint(
                fields=("tenant", "organization", "serial_number"),
                condition=~models.Q(serial_number=""),
                name="unique_hardware_serial_in_org",
                nulls_distinct=False,
            ),
            models.UniqueConstraint(
                fields=("tenant", "organization", "asset_tag"),
                condition=~models.Q(asset_tag=""),
                name="unique_hardware_tag_in_org",
                nulls_distinct=False,
            ),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "lifecycle_state"), name="core_hwasset_scope_idx")]

    def __str__(self) -> str:
        return f"Hardware profile for {self.asset_id}"

    def clean(self) -> None:
        if self.asset_id and (
            self.asset.tenant_id != self.tenant_id
            or self.asset.organization_id != self.organization_id
            or self.asset.product.kind != CatalogProductKind.HARDWARE
        ):
            raise ValidationError("Hardware profile must use an exact client hardware asset scope")
        if self.warranty_starts_on and self.warranty_ends_on and self.warranty_ends_on < self.warranty_starts_on:
            raise ValidationError("Warranty end date cannot precede its start date")
        for target in (self.assigned_person, self.assigned_site, self.assigned_location):
            if target is not None and (
                target.tenant_id != self.tenant_id or target.organization_id != self.organization_id
            ):
                raise ValidationError("Hardware assignment targets must use the asset's client scope")
        assigned_location = self.assigned_location if self.assigned_location_id else None
        if assigned_location is not None and self.assigned_site_id != assigned_location.site_id:
            raise ValidationError("Hardware assignment location must belong to its selected site")
        if self.lifecycle_state == HardwareLifecycleState.DISPOSED:
            if not self.disposed_on or not self.disposal_method:
                raise ValidationError("Disposed hardware requires a date and method")
            if self.assigned_person_id or self.assigned_site_id or self.assigned_location_id or self.assigned_at:
                raise ValidationError("Disposed hardware cannot retain a current assignment")
        elif self.disposed_on or self.disposal_method or self.disposal_reason:
            raise ValidationError("Disposal details require the disposed lifecycle state")


class HardwareLifecycleEventType(models.TextChoices):
    CREATED = "created", "Created"
    DETAILS_UPDATED = "details_updated", "Details updated"
    STATE_CHANGED = "state_changed", "State changed"
    ASSIGNED = "assigned", "Assigned"
    UNASSIGNED = "unassigned", "Unassigned"
    DISPOSED = "disposed", "Disposed"


class ClientAssetLifecycleEvent(models.Model):
    """Append-only, value-minimized history for one client hardware asset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="client_asset_lifecycle_events")
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="client_asset_lifecycle_events",
        null=True,
        blank=True,
    )
    asset = models.ForeignKey(ClientAsset, on_delete=models.PROTECT, related_name="lifecycle_events")
    event_type = models.CharField(max_length=32, choices=HardwareLifecycleEventType.choices)
    from_state = models.CharField(max_length=24, blank=True)
    to_state = models.CharField(max_length=24, blank=True)
    person = models.ForeignKey("PersonAssociation", on_delete=models.PROTECT, null=True, blank=True)
    site = models.ForeignKey("Site", on_delete=models.PROTECT, null=True, blank=True)
    location = models.ForeignKey("Location", on_delete=models.PROTECT, null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-occurred_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(event_type__in=HardwareLifecycleEventType.values),
                name="hardware_event_type_valid",
            )
        ]
        indexes = [
            models.Index(
                fields=("tenant", "organization", "asset", "occurred_at"),
                name="core_hwevent_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.asset_id}: {self.event_type}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Hardware lifecycle events are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Hardware lifecycle events are append-only")

    def clean(self) -> None:
        if self.asset_id and (
            self.asset.tenant_id != self.tenant_id or self.asset.organization_id != self.organization_id
        ):
            raise ValidationError("Hardware lifecycle event must use its asset scope")
        for target in (self.person, self.site, self.location):
            if target is not None and (
                target.tenant_id != self.tenant_id or target.organization_id != self.organization_id
            ):
                raise ValidationError("Lifecycle assignment targets must use the asset's client scope")
        location = self.location if self.location_id else None
        if location is not None and self.site_id != location.site_id:
            raise ValidationError("Lifecycle event location must belong to its selected site")


class SoftwareInstallationStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    INSTALLED = "installed", "Installed"
    SUSPENDED = "suspended", "Suspended"
    UNINSTALLED = "uninstalled", "Uninstalled"


class SoftwareLicenseKind(models.TextChoices):
    SUBSCRIPTION = "subscription", "Subscription"
    PERPETUAL = "perpetual", "Perpetual"
    TRIAL = "trial", "Trial"


class SoftwareLicenseStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    EXPIRED = "expired", "Expired"
    TERMINATED = "terminated", "Terminated"


class SoftwareRenewalInterval(models.TextChoices):
    NONE = "none", "None"
    MONTHLY = "monthly", "Monthly"
    ANNUAL = "annual", "Annual"
    MULTI_YEAR = "multi_year", "Multi-year"


class ClientSoftwareInstallation(TimestampedModel):
    """Current installation state for one client-owned software asset."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="client_software_installations")
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="client_software_installations",
        null=True,
        blank=True,
    )
    asset = models.OneToOneField(ClientAsset, on_delete=models.PROTECT, related_name="software_installation")
    status = models.CharField(
        max_length=20, choices=SoftwareInstallationStatus.choices, default=SoftwareInstallationStatus.PLANNED
    )
    installed_version = models.CharField(max_length=160, blank=True)
    installed_on = models.DateField(null=True, blank=True)
    last_verified_on = models.DateField(null=True, blank=True)
    site = models.ForeignKey(
        "Site", on_delete=models.PROTECT, null=True, blank=True, related_name="software_installations"
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=SoftwareInstallationStatus.values),
                name="software_installation_status_valid",
            )
        ]
        indexes = [models.Index(fields=("tenant", "organization", "status"), name="core_swinstall_scope_idx")]

    def __str__(self) -> str:
        return f"Software installation for {self.asset_id}"

    def clean(self) -> None:
        if self.asset_id and (
            self.asset.tenant_id != self.tenant_id
            or self.asset.organization_id != self.organization_id
            or self.asset.product.kind != CatalogProductKind.SOFTWARE
        ):
            raise ValidationError("Software installation must use an exact client software asset scope")
        site = self.site if self.site_id else None
        if site is not None and (site.tenant_id != self.tenant_id or site.organization_id != self.organization_id):
            raise ValidationError("Software installation site must use the asset's client scope")
        if self.status == SoftwareInstallationStatus.INSTALLED and not self.installed_on:
            raise ValidationError("Installed software requires an installation date")


class SoftwareLicense(TimestampedModel):
    """Addressable client entitlement related to one retained software product."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="software_licenses")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="software_licenses", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="software_license")
    supplier = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="supplied_software_licenses")
    product = models.ForeignKey(CatalogProduct, on_delete=models.PROTECT, related_name="software_licenses")
    model = models.ForeignKey(
        CatalogModel, on_delete=models.PROTECT, null=True, blank=True, related_name="software_licenses"
    )
    kind = models.CharField(max_length=20, choices=SoftwareLicenseKind.choices)
    status = models.CharField(
        max_length=20, choices=SoftwareLicenseStatus.choices, default=SoftwareLicenseStatus.ACTIVE
    )
    seat_limit = models.PositiveIntegerField(default=1)
    starts_on = models.DateField(null=True, blank=True)
    renews_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    renewal_interval = models.CharField(
        max_length=20, choices=SoftwareRenewalInterval.choices, default=SoftwareRenewalInterval.NONE
    )
    auto_renew = models.BooleanField(default=False)
    reference = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="software_licenses"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(seat_limit__gte=1), name="software_license_seat_limit_positive"),
            models.CheckConstraint(
                condition=models.Q(kind__in=SoftwareLicenseKind.values), name="software_license_kind_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=SoftwareLicenseStatus.values), name="software_license_status_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(renewal_interval__in=SoftwareRenewalInterval.values),
                name="software_renewal_interval_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "status", "renews_on"), name="core_swlicense_scope_idx")
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Software license and entity scopes must match")
        if self.product_id and (
            self.product.tenant_id != self.tenant_id
            or self.product.organization_id != self.supplier_id
            or self.product.kind != CatalogProductKind.SOFTWARE
        ):
            raise ValidationError("Software license requires a retained supplier software product")
        catalog_model = self.model if self.model_id else None
        if catalog_model is not None and (
            catalog_model.product_id != self.product_id or catalog_model.organization_id != self.supplier_id
        ):
            raise ValidationError("Software license model must belong to its supplier product")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError("License end date cannot precede its start date")
        if self.starts_on and self.renews_on and self.renews_on < self.starts_on:
            raise ValidationError("Renewal date cannot precede the license start date")
        if self.kind == SoftwareLicenseKind.PERPETUAL and (
            self.auto_renew or self.renewal_interval != SoftwareRenewalInterval.NONE
        ):
            raise ValidationError("Perpetual licenses cannot auto-renew or use a renewal interval")


class SoftwareLicenseInstallation(models.Model):
    """Explicit relationship between an entitlement and a covered installation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="software_license_installations")
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="software_license_installations",
        null=True,
        blank=True,
    )
    license = models.ForeignKey(SoftwareLicense, on_delete=models.PROTECT, related_name="installation_links")
    installation = models.ForeignKey(ClientSoftwareInstallation, on_delete=models.PROTECT, related_name="license_links")
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("license", "installation"), name="unique_license_installation")]
        indexes = [models.Index(fields=("tenant", "organization", "license"), name="core_swlicinst_scope_idx")]

    def __str__(self) -> str:
        return f"{self.license_id}: {self.installation_id}"

    def clean(self) -> None:
        if (
            self.license_id
            and self.installation_id
            and (
                self.license.tenant_id != self.tenant_id
                or self.license.organization_id != self.organization_id
                or self.installation.tenant_id != self.tenant_id
                or self.installation.organization_id != self.organization_id
                or self.installation.asset.product_id != self.license.product_id
            )
        ):
            raise ValidationError("License and installation must share client scope and software product")


class SoftwareLicenseSeat(models.Model):
    """One retained seat allocation within a client entitlement."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="software_license_seats")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="software_license_seats", null=True, blank=True
    )
    license = models.ForeignKey(SoftwareLicense, on_delete=models.PROTECT, related_name="seats")
    seat_number = models.PositiveIntegerField()
    person = models.ForeignKey(
        "PersonAssociation", on_delete=models.PROTECT, null=True, blank=True, related_name="software_license_seats"
    )
    installation = models.ForeignKey(
        ClientSoftwareInstallation, on_delete=models.PROTECT, null=True, blank=True, related_name="license_seats"
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("license", "seat_number"), name="unique_software_license_seat_number"),
            models.CheckConstraint(
                condition=models.Q(seat_number__gte=1), name="software_license_seat_number_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(person__isnull=False) | models.Q(installation__isnull=False),
                name="software_seat_has_target",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "license", "revoked_at"), name="core_swseat_scope_idx")
        ]

    def __str__(self) -> str:
        return f"{self.license_id}: seat {self.seat_number}"

    def clean(self) -> None:
        if self.license_id and (
            self.license.tenant_id != self.tenant_id or self.license.organization_id != self.organization_id
        ):
            raise ValidationError("Software seat and license scopes must match")
        for target in (self.person, self.installation):
            if target is not None and (
                target.tenant_id != self.tenant_id or target.organization_id != self.organization_id
            ):
                raise ValidationError("Software seat targets must use the license's client scope")
        installation = self.installation if self.installation_id else None
        if installation is not None and installation.asset.product_id != self.license.product_id:
            raise ValidationError("Software seat installation must use the licensed product")


class SoftwareLicenseEventType(models.TextChoices):
    CREATED = "created", "Created"
    DETAILS_UPDATED = "details_updated", "Details updated"
    INSTALLATION_LINKED = "installation_linked", "Installation linked"
    INSTALLATION_UNLINKED = "installation_unlinked", "Installation unlinked"
    SEAT_ASSIGNED = "seat_assigned", "Seat assigned"
    SEAT_REVOKED = "seat_revoked", "Seat revoked"


class SoftwareLicenseEvent(models.Model):
    """Append-only, value-minimized licensing lifecycle history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="software_license_events")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="software_license_events", null=True, blank=True
    )
    license = models.ForeignKey(SoftwareLicense, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=32, choices=SoftwareLicenseEventType.choices)
    installation = models.ForeignKey(ClientSoftwareInstallation, on_delete=models.PROTECT, null=True, blank=True)
    person = models.ForeignKey("PersonAssociation", on_delete=models.PROTECT, null=True, blank=True)
    seat_number = models.PositiveIntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-occurred_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(event_type__in=SoftwareLicenseEventType.values),
                name="software_license_event_type_valid",
            )
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "license", "occurred_at"), name="core_swlicevent_scope_idx")
        ]

    def __str__(self) -> str:
        return f"{self.license_id}: {self.event_type}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Software license events are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Software license events are append-only")

    def clean(self) -> None:
        if self.license_id and (
            self.license.tenant_id != self.tenant_id or self.license.organization_id != self.organization_id
        ):
            raise ValidationError("Software license event must use its license scope")
        for target in (self.installation, self.person):
            if target is not None and (
                target.tenant_id != self.tenant_id or target.organization_id != self.organization_id
            ):
                raise ValidationError("Software license event targets must use its client scope")


class CommercialContractKind(models.TextChoices):
    SERVICE = "service", "Service"
    SUPPORT = "support", "Support"
    LEASE = "lease", "Lease"
    SUBSCRIPTION = "subscription", "Subscription"
    OTHER = "other", "Other"


class CommercialContractStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    TERMINATED = "terminated", "Terminated"


class CostBillingInterval(models.TextChoices):
    ONE_TIME = "one_time", "One time"
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    ANNUAL = "annual", "Annual"


class CommercialContract(TimestampedModel):
    """Client-scoped commercial agreement whose financial terms are projected separately."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="commercial_contracts")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="commercial_contracts", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="commercial_contract")
    provider = models.ForeignKey("Organization", on_delete=models.PROTECT, related_name="provided_commercial_contracts")
    kind = models.CharField(max_length=24, choices=CommercialContractKind.choices)
    status = models.CharField(
        max_length=24, choices=CommercialContractStatus.choices, default=CommercialContractStatus.DRAFT
    )
    description = models.CharField(max_length=1000, blank=True)
    reference = models.CharField(max_length=240, blank=True)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    renews_on = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    renewal_notice_days = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="commercial_contracts"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=CommercialContractKind.values), name="commercial_contract_kind_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=CommercialContractStatus.values),
                name="commercial_contract_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(renewal_notice_days__lte=3650),
                name="commercial_contract_notice_days_bounded",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "status", "renews_on"), name="core_contract_scope_idx"),
            models.Index(fields=("tenant", "organization", "provider"), name="core_contract_provider_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "commercial_contract"
            or self.entity.visibility != EntityVisibility.MSP_PRIVATE
        ):
            raise ValidationError("Commercial contract entity identity, scope, and visibility must match")
        organization = self.organization if self.organization_id else None
        if organization is not None and organization.tenant_id != self.tenant_id:
            raise ValidationError("Commercial contract organization must belong to its tenant")
        if self.provider_id and (self.provider.tenant_id != self.tenant_id or self.provider_id == self.organization_id):
            raise ValidationError("Commercial contract provider must be another organization in the same tenant")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError("Contract end date cannot precede its start date")
        if self.starts_on and self.renews_on and self.renews_on < self.starts_on:
            raise ValidationError("Contract renewal date cannot precede its start date")


class ContractCost(TimestampedModel):
    """A sensitive commercial line item that is never projected without costs.view."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="contract_costs")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="contract_costs", null=True, blank=True
    )
    contract = models.ForeignKey(CommercialContract, on_delete=models.PROTECT, related_name="costs")
    label = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    billing_interval = models.CharField(max_length=16, choices=CostBillingInterval.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=240, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("label", "id")
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="contract_cost_amount_nonnegative"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="contract_cost_quantity_positive"),
            models.CheckConstraint(
                condition=models.Q(billing_interval__in=CostBillingInterval.values),
                name="contract_cost_interval_valid",
            ),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "contract"), name="core_contract_cost_scope_idx")]

    def __str__(self) -> str:
        return self.label

    def clean(self) -> None:
        if self.contract_id and (
            self.contract.tenant_id != self.tenant_id or self.contract.organization_id != self.organization_id
        ):
            raise ValidationError("Contract cost must use its contract scope")
        if self.currency and (len(self.currency) != 3 or not self.currency.isascii() or not self.currency.isalpha()):
            raise ValidationError("Currency must be a three-letter currency code")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError("Cost end date cannot precede its start date")


class ClientAssetDocumentProvenance(models.Model):
    """Append-only client projection of one exact supplier STATIC publication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="client_asset_documents")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="client_asset_documents", null=True, blank=True
    )
    asset = models.ForeignKey(ClientAsset, on_delete=models.PROTECT, related_name="document_provenance")
    catalog_document = models.ForeignKey(
        CatalogProductDocument, on_delete=models.PROTECT, related_name="client_asset_provenance"
    )
    publication = models.ForeignKey(
        "DocumentPublication", on_delete=models.PROTECT, related_name="client_asset_provenance"
    )
    content_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("publication__title", "id")
        constraints = [models.UniqueConstraint(fields=("asset", "publication"), name="unique_client_asset_publication")]
        indexes = [models.Index(fields=("tenant", "organization", "asset"), name="core_assetdoc_scope_idx")]

    def __str__(self) -> str:
        return f"{self.asset_id}: {self.publication_id}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ValidationError("Client asset document provenance is append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Client asset document provenance is append-only")

    def clean(self) -> None:
        if self.asset_id and (
            self.asset.tenant_id != self.tenant_id or self.asset.organization_id != self.organization_id
        ):
            raise ValidationError("Asset document provenance must use its asset scope")
        if self.catalog_document_id and (
            self.catalog_document.tenant_id != self.tenant_id
            or self.catalog_document.organization_id != self.asset.supplier_id
            or self.catalog_document.product_id != self.asset.product_id
            or self.catalog_document.model_id not in {None, self.asset.model_id}
        ):
            raise ValidationError("Asset document provenance does not apply to the retained model")
        if self.publication_id and (
            self.publication_id != self.catalog_document.publication_id
            or self.publication.content_digest != self.content_digest
        ):
            raise ValidationError("Asset document publication identity or digest does not match")


class OrganizationAccessMode(models.TextChoices):
    ALL_AUTHORIZED = "all_authorized", "All authorized MSP staff"
    ASSIGNED_ONLY = "assigned_only", "Assigned MSP staff only"


class Organization(TimestampedModel):
    """A tenant-owned business organization anchored to one universal entity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="organizations")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="organization_record")
    legal_name = models.CharField(max_length=240, blank=True)
    website = models.URLField(max_length=500, blank=True)
    access_mode = models.CharField(
        max_length=32,
        choices=OrganizationAccessMode.choices,
        default=OrganizationAccessMode.ALL_AUTHORIZED,
    )

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(access_mode__in=OrganizationAccessMode.values),
                name="organization_access_mode_valid",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "access_mode", "entity"], name="core_org_tenant_access_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        creating = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creating:
                Workspace.objects.create(
                    id=workspace_identity_uuid(tenant_id=self.tenant_id, organization_id=self.id),
                    tenant=self.tenant,
                    kind=WorkspaceKind.ORGANIZATION,
                    organization=self,
                )

    def clean(self) -> None:
        if self.entity_id and self.tenant_id != self.entity.tenant_id:
            raise ValidationError("Organization entity must belong to the organization tenant")
        if self.entity_id and self.entity.organization_id is not None:
            raise ValidationError("An organization anchor cannot itself be organization-scoped")


class OrganizationKind(models.TextChoices):
    CLIENT = "client", "Client"
    VENDOR = "vendor", "Vendor"
    MANUFACTURER = "manufacturer", "Manufacturer"
    PARTNER = "partner", "Partner"


class OrganizationClassification(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="organization_classifications")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="classifications")
    kind = models.CharField(max_length=32, choices=OrganizationKind.choices)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind"],
                name="unique_organization_classification",
            )
        ]
        indexes = [models.Index(fields=["tenant", "kind", "organization"])]

    def __str__(self) -> str:
        return f"{self.organization_id} {self.kind}"

    def clean(self) -> None:
        if self.organization_id and self.tenant_id != self.organization.tenant_id:
            raise ValidationError("Organization classification must belong to its tenant")


class Site(TimestampedModel):
    """An addressable physical or operational site in one workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="sites")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="sites",
        null=True,
        blank=True,
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="site_record")
    code = models.CharField(max_length=64, blank=True)
    address_line_1 = models.CharField(max_length=240, blank=True)
    address_line_2 = models.CharField(max_length=240, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    phone = models.CharField(max_length=64, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "organization", "code"],
                condition=~models.Q(code=""),
                name="unique_site_code_in_workspace",
                nulls_distinct=False,
            )
        ]
        indexes = [models.Index(fields=["tenant", "organization", "archived_at"])]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if organization is not None and self.tenant_id != organization.tenant_id:
            raise ValidationError("Site organization must belong to its tenant")
        if self.entity_id and self.tenant_id != self.entity.tenant_id:
            raise ValidationError("Site entity must belong to the site tenant")
        if self.entity_id and self.entity.organization_id != self.organization_id:
            raise ValidationError("Site entity must use the site's workspace scope")


class LocationKind(models.TextChoices):
    BUILDING = "building", "Building"
    FLOOR = "floor", "Floor"
    SUITE = "suite", "Suite"
    ROOM = "room", "Room"
    OFFICE = "office", "Office"
    DESK = "desk", "Desk"
    AREA = "area", "Area"


class Location(TimestampedModel):
    """An addressable hierarchical place within one site."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="locations")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="locations",
        null=True,
        blank=True,
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="location_record")
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="locations")
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=32, choices=LocationKind.choices)
    code = models.CharField(max_length=64, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(parent=models.F("id")), name="location_not_own_parent"),
            models.UniqueConstraint(
                fields=["site", "parent", "code"],
                condition=~models.Q(code=""),
                name="unique_location_code_under_parent",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "organization", "site", "archived_at"]),
            models.Index(fields=["site", "parent", "kind"]),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if organization is not None and self.tenant_id != organization.tenant_id:
            raise ValidationError("Location organization must belong to its tenant")
        if self.entity_id and self.tenant_id != self.entity.tenant_id:
            raise ValidationError("Location entity must belong to the location tenant")
        if self.entity_id and self.entity.organization_id != self.organization_id:
            raise ValidationError("Location entity must use the location's workspace scope")
        site = self.site if self.site_id else None
        if site is not None and (site.tenant_id != self.tenant_id or site.organization_id != self.organization_id):
            raise ValidationError("Location site must use the location's workspace scope")
        parent = self.parent if self.parent_id else None
        if parent is not None and (parent.site_id != self.site_id or self.parent_id == self.id):
            raise ValidationError("Location parent must be a different location in the same site")


class CustomFieldType(models.TextChoices):
    TEXT = "text", "Text"
    INTEGER = "integer", "Integer"
    NUMBER = "number", "Number"
    BOOLEAN = "boolean", "Boolean"
    DATE = "date", "Date"
    URL = "url", "URL"
    EMAIL = "email", "Email"
    CHOICE = "choice", "Choice"
    MULTI_CHOICE = "multi_choice", "Multiple choice"


class CustomFieldDefinition(TimestampedModel):
    """Stable identity and ownership for a versioned custom field."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="custom_field_definitions")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="custom_field_definitions",
        null=True,
        blank=True,
    )
    key = models.SlugField(max_length=80)
    entity_type = models.CharField(max_length=80)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "organization", "entity_type", "key"],
                name="unique_custom_field_key_in_scope",
                nulls_distinct=False,
            )
        ]
        indexes = [
            models.Index(
                fields=["tenant", "organization", "entity_type", "archived_at"],
                name="core_cfdef_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.entity_type}.{self.key}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Custom-field definitions change only through versioning and archival services")
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if organization is not None and organization.tenant_id != self.tenant_id:
            raise ValidationError("Custom-field organization must belong to its tenant")


class CustomFieldDefinitionVersion(models.Model):
    """Immutable validation and presentation contract for one definition revision."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="custom_field_definition_versions")
    definition = models.ForeignKey(CustomFieldDefinition, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    label = models.CharField(max_length=160)
    description = models.CharField(max_length=500, blank=True)
    required = models.BooleanField(default=False)
    field_type = models.CharField(max_length=32, choices=CustomFieldType.choices)
    schema = models.JSONField()
    display_order = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="custom_field_definition_versions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["definition", "version"], name="unique_custom_field_definition_version"),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="custom_field_version_positive"),
        ]
        ordering = ("definition_id", "version")

    def __str__(self) -> str:
        return f"{self.definition_id} v{self.version}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Custom-field definition versions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Custom-field definition versions are immutable")

    def clean(self) -> None:
        if self.definition_id and self.definition.tenant_id != self.tenant_id:
            raise ValidationError("Custom-field version must belong to the definition tenant")


class Person(TimestampedModel):
    """One tenant-wide human identity anchored to the entity registry."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="people")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="person_record")
    preferred_name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.EmailField(max_length=254, blank=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        indexes = [models.Index(fields=["tenant", "created_at"])]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and self.tenant_id != self.entity.tenant_id:
            raise ValidationError("Person entity must belong to the person tenant")
        if self.entity_id and self.entity.organization_id is not None:
            raise ValidationError("A person identity must remain tenant-scoped")


class PersonAssociationKind(models.TextChoices):
    EMPLOYEE = "employee", "Employee"
    CONTACT = "contact", "Contact"


class PersonAssociation(TimestampedModel):
    """A person's employment or contact role in one explicit workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="person_associations")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="person_associations",
        null=True,
        blank=True,
    )
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="associations")
    kind = models.CharField(max_length=32, choices=PersonAssociationKind.choices)
    role = models.CharField(max_length=160, blank=True)
    responsibility = models.CharField(max_length=240, blank=True)
    location = models.CharField(max_length=160, blank=True)
    office = models.CharField(max_length=120, blank=True)
    site = models.ForeignKey(
        Site,
        on_delete=models.PROTECT,
        related_name="person_associations",
        null=True,
        blank=True,
    )
    structured_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="person_associations",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["person", "organization"],
                condition=models.Q(organization__isnull=False),
                name="unique_person_organization_association",
            ),
            models.UniqueConstraint(
                fields=["person"],
                condition=models.Q(organization__isnull=True),
                name="unique_person_msp_association",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "organization", "archived_at"]),
            models.Index(fields=["tenant", "kind", "organization"]),
        ]

    def __str__(self) -> str:
        return f"{self.person_id} in {self.organization_id or 'MSP'}"

    def clean(self) -> None:
        if self.person_id and self.tenant_id != self.person.tenant_id:
            raise ValidationError("Person association must belong to the person tenant")
        organization = self.organization if self.organization_id else None
        if organization is not None and self.tenant_id != organization.tenant_id:
            raise ValidationError("Person association organization must belong to its tenant")
        site = self.site if self.site_id else None
        if site is not None and (site.tenant_id != self.tenant_id or site.organization_id != self.organization_id):
            raise ValidationError("Person association site must use its workspace scope")
        structured_location = self.structured_location if self.structured_location_id else None
        if structured_location is not None:
            if self.site_id != structured_location.site_id:
                raise ValidationError("Person association location must belong to its selected site")
            if (
                structured_location.tenant_id != self.tenant_id
                or structured_location.organization_id != self.organization_id
            ):
                raise ValidationError("Person association location must use its workspace scope")


class NetworkRackStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class NetworkRack(TimestampedModel):
    """An addressable equipment rack in one exact physical Workspace location."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_racks")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_racks", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_rack")
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="network_racks")
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="network_racks", null=True, blank=True
    )
    unit_count = models.PositiveSmallIntegerField(default=42)
    status = models.CharField(max_length=16, choices=NetworkRackStatus.choices, default=NetworkRackStatus.ACTIVE)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(unit_count__gte=1, unit_count__lte=100), name="rack_units_valid"),
            models.CheckConstraint(condition=models.Q(status__in=NetworkRackStatus.values), name="rack_status_valid"),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "site"), name="core_netrack_scope_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network rack and entity scopes must match")
        if self.site_id and (
            self.site.tenant_id != self.tenant_id or self.site.organization_id != self.organization_id
        ):
            raise ValidationError("Network rack site must use its Workspace scope")
        location = self.location if self.location_id else None
        if location is not None and (
            location.tenant_id != self.tenant_id
            or location.organization_id != self.organization_id
            or location.site_id != self.site_id
        ):
            raise ValidationError("Network rack location must belong to its selected site and Workspace")


class NetworkDeviceRole(models.TextChoices):
    ROUTER = "router", "Router"
    SWITCH = "switch", "Switch"
    FIREWALL = "firewall", "Firewall"
    WIRELESS_CONTROLLER = "wireless_controller", "Wireless controller"
    ACCESS_POINT = "access_point", "Access point"
    LOAD_BALANCER = "load_balancer", "Load balancer"
    OTHER = "other", "Other"


class NetworkDeviceStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    OFFLINE = "offline", "Offline"
    RETIRED = "retired", "Retired"


class NetworkDevice(TimestampedModel):
    """A network role and physical placement backed by one hardware asset.

    ``legacy_unbacked`` exists only to preserve pre-0.4.9 rows whose original
    creation preceded the asset requirement. New application records may not set it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_devices")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_devices", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_device")
    role = models.CharField(max_length=32, choices=NetworkDeviceRole.choices)
    status = models.CharField(max_length=16, choices=NetworkDeviceStatus.choices, default=NetworkDeviceStatus.ACTIVE)
    hardware_asset = models.OneToOneField(
        ClientAsset,
        on_delete=models.PROTECT,
        related_name="network_device",
        null=True,
        blank=True,
    )
    legacy_unbacked = models.BooleanField(default=False)
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="network_devices", null=True, blank=True)
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="network_devices", null=True, blank=True
    )
    rack = models.ForeignKey(
        NetworkRack, on_delete=models.PROTECT, related_name="network_devices", null=True, blank=True
    )
    rack_unit = models.PositiveSmallIntegerField(null=True, blank=True)
    rack_units = models.PositiveSmallIntegerField(default=1)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=NetworkDeviceRole.values), name="network_device_role_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=NetworkDeviceStatus.values), name="network_device_status_valid"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(rack__isnull=True, rack_unit__isnull=True, rack_units=1)
                    | models.Q(rack__isnull=False, rack_unit__isnull=False, rack_units__gte=1, rack_units__lte=100)
                ),
                name="network_device_rack_placement_complete",
            ),
            models.CheckConstraint(
                condition=models.Q(location__isnull=True) | models.Q(site__isnull=False),
                name="network_device_location_requires_site",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "role"), name="core_netdevice_scope_idx"),
            models.Index(fields=("rack", "rack_unit"), name="core_netdevice_rack_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network device and entity scopes must match")
        hardware_asset = self.hardware_asset if self.hardware_asset_id else None
        if hardware_asset is not None and (
            hardware_asset.tenant_id != self.tenant_id
            or hardware_asset.organization_id != self.organization_id
            or hardware_asset.product.kind != CatalogProductKind.HARDWARE
        ):
            raise ValidationError("Network device hardware asset must be hardware in the same Workspace")
        if hardware_asset is None and not self.legacy_unbacked:
            raise ValidationError("Network devices require a hardware asset")
        if hardware_asset is not None and self.legacy_unbacked:
            raise ValidationError("Asset-backed network devices cannot retain the legacy marker")
        site = self.site if self.site_id else None
        if site is not None and (site.tenant_id != self.tenant_id or site.organization_id != self.organization_id):
            raise ValidationError("Network device site must use its Workspace scope")
        location = self.location if self.location_id else None
        if location is not None and (
            location.tenant_id != self.tenant_id
            or location.organization_id != self.organization_id
            or location.site_id != self.site_id
        ):
            raise ValidationError("Network device location must belong to its selected site and Workspace")
        rack = self.rack if self.rack_id else None
        if rack is not None and (
            rack.tenant_id != self.tenant_id
            or rack.organization_id != self.organization_id
            or rack.site_id != self.site_id
            or rack.location_id != self.location_id
        ):
            raise ValidationError("Network device rack must match its physical Workspace location")


class NetworkVRF(TimestampedModel):
    """An isolated routing namespace in one exact Workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_vrfs")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_vrfs", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_vrf")
    route_distinguisher = models.CharField(max_length=64, blank=True)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        indexes = [models.Index(fields=("tenant", "organization"), name="core_netvrf_scope_idx")]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network VRF and entity scopes must match")


class NetworkVLAN(TimestampedModel):
    """A VLAN identifier owned by one exact Workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_vlans")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_vlans", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_vlan")
    vlan_id = models.PositiveSmallIntegerField()
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("vlan_id", "entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(vlan_id__gte=1, vlan_id__lte=4094), name="network_vlan_id_valid"),
            models.UniqueConstraint(
                fields=("tenant", "organization", "vlan_id"),
                name="network_vlan_id_unique_in_workspace",
                nulls_distinct=False,
            ),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "vlan_id"), name="core_netvlan_scope_idx")]

    def __str__(self) -> str:
        return f"{self.vlan_id} · {self.entity.display_name}"

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network VLAN and entity scopes must match")


class NetworkSubnet(TimestampedModel):
    """A canonical IP prefix in the default table or one explicit VRF."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_subnets")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_subnets", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_subnet")
    cidr = models.CharField(max_length=49)
    address_family = models.PositiveSmallIntegerField()
    vrf = models.ForeignKey(NetworkVRF, on_delete=models.PROTECT, related_name="subnets", null=True, blank=True)
    vlan = models.ForeignKey(NetworkVLAN, on_delete=models.PROTECT, related_name="subnets", null=True, blank=True)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("address_family", "cidr", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(address_family__in=(4, 6)), name="network_subnet_family_valid"),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "vrf"), name="core_netsubnet_scope_idx"),
            models.Index(fields=("tenant", "organization", "cidr"), name="core_netsubnet_cidr_idx"),
        ]

    def __str__(self) -> str:
        return self.cidr

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network subnet and entity scopes must match")
        for related, label in (
            (self.vrf if self.vrf_id else None, "VRF"),
            (self.vlan if self.vlan_id else None, "VLAN"),
        ):
            if related is not None and (
                related.tenant_id != self.tenant_id or related.organization_id != self.organization_id
            ):
                raise ValidationError(f"Network subnet {label} must use its Workspace scope")


class NetworkInterfaceKind(models.TextChoices):
    PHYSICAL = "physical", "Physical"
    VIRTUAL = "virtual", "Virtual"
    LAG = "lag", "Link aggregation"
    LOOPBACK = "loopback", "Loopback"
    TUNNEL = "tunnel", "Tunnel"
    WIRELESS = "wireless", "Wireless"
    OTHER = "other", "Other"


class NetworkInterfaceStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"
    RETIRED = "retired", "Retired"


class NetworkInterface(TimestampedModel):
    """A stable logical or physical interface on one network device."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_interfaces")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_interfaces", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_interface")
    device = models.ForeignKey(NetworkDevice, on_delete=models.PROTECT, related_name="interfaces")
    kind = models.CharField(max_length=24, choices=NetworkInterfaceKind.choices)
    status = models.CharField(max_length=24, choices=NetworkInterfaceStatus.choices)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("device__entity__display_name", "entity__display_name", "entity_id")
        indexes = [models.Index(fields=("tenant", "organization", "device"), name="core_netif_scope_idx")]

    def __str__(self) -> str:
        return f"{self.device.entity.display_name} · {self.entity.display_name}"

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network interface and entity scopes must match")
        if self.device_id and (
            self.device.tenant_id != self.tenant_id or self.device.organization_id != self.organization_id
        ):
            raise ValidationError("Network interface device must use its Workspace scope")


class NetworkIPAddressStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    RESERVED = "reserved", "Reserved"
    DHCP = "dhcp", "DHCP"
    DEPRECATED = "deprecated", "Deprecated"


class NetworkIPAddress(TimestampedModel):
    """A canonical host address within one subnet and routing namespace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_ip_addresses")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_ip_addresses", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_ip_address")
    subnet = models.ForeignKey(NetworkSubnet, on_delete=models.PROTECT, related_name="ip_addresses")
    interface = models.ForeignKey(
        NetworkInterface, on_delete=models.PROTECT, related_name="ip_addresses", null=True, blank=True
    )
    hardware_asset = models.ForeignKey(
        ClientAsset, on_delete=models.PROTECT, related_name="network_ip_addresses", null=True, blank=True
    )
    address = models.CharField(max_length=45)
    address_family = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=24, choices=NetworkIPAddressStatus.choices)
    dns_name = models.CharField(max_length=253, blank=True)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("address_family", "address", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(address_family__in=(4, 6)), name="network_ip_family_valid")
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "subnet"), name="core_netip_scope_idx"),
            models.Index(fields=("tenant", "organization", "address"), name="core_netip_address_idx"),
            models.Index(fields=("tenant", "organization", "hardware_asset"), name="core_netip_asset_idx"),
        ]

    def __str__(self) -> str:
        return self.address

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network IP address and entity scopes must match")
        for related, label in (
            (self.subnet if self.subnet_id else None, "subnet"),
            (self.interface if self.interface_id else None, "interface"),
            (self.hardware_asset if self.hardware_asset_id else None, "hardware asset"),
        ):
            if related is not None and (
                related.tenant_id != self.tenant_id or related.organization_id != self.organization_id
            ):
                raise ValidationError(f"Network IP address {label} must use its Workspace scope")
        hardware_asset = self.hardware_asset if self.hardware_asset_id else None
        if hardware_asset is not None and hardware_asset.product.kind != CatalogProductKind.HARDWARE:
            raise ValidationError("Network IP address assignment requires a hardware asset")
        interface = self.interface if self.interface_id else None
        if interface is not None and hardware_asset is not None:
            interface_asset_id = interface.device.hardware_asset_id
            if interface_asset_id is not None and interface_asset_id != hardware_asset.id:
                raise ValidationError("Network IP address legacy interface and hardware asset must agree")


class NetworkMACAddress(TimestampedModel):
    """A canonical EUI-48 address assigned directly to hardware or retained legacy interface data."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_mac_addresses")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_mac_addresses", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_mac_address")
    interface = models.ForeignKey(
        NetworkInterface, on_delete=models.PROTECT, related_name="mac_addresses", null=True, blank=True
    )
    hardware_asset = models.ForeignKey(
        ClientAsset, on_delete=models.PROTECT, related_name="network_mac_addresses", null=True, blank=True
    )
    address = models.CharField(max_length=17)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("address", "entity_id")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "organization", "address"),
                name="network_mac_unique_in_workspace",
                nulls_distinct=False,
            )
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "interface"), name="core_netmac_scope_idx"),
            models.Index(fields=("tenant", "organization", "hardware_asset"), name="core_netmac_asset_idx"),
        ]

    def __str__(self) -> str:
        return self.address

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Network MAC address and entity scopes must match")
        if (
            self.interface_id
            and self.interface is not None
            and (self.interface.tenant_id != self.tenant_id or self.interface.organization_id != self.organization_id)
        ):
            raise ValidationError("Network MAC address interface must use its Workspace scope")
        hardware_asset = self.hardware_asset if self.hardware_asset_id else None
        if hardware_asset is not None and (
            hardware_asset.tenant_id != self.tenant_id
            or hardware_asset.organization_id != self.organization_id
            or hardware_asset.product.kind != CatalogProductKind.HARDWARE
        ):
            raise ValidationError("Network MAC address assignment requires same-Workspace hardware")
        interface = self.interface if self.interface_id else None
        if interface is not None and hardware_asset is not None:
            interface_asset_id = interface.device.hardware_asset_id
            if interface_asset_id is not None and interface_asset_id != hardware_asset.id:
                raise ValidationError("Network MAC address legacy interface and hardware asset must agree")


class NetBoxObjectType(models.TextChoices):
    RACK = "dcim.rack", "Rack"
    DEVICE = "dcim.device", "Device"
    MAC_ADDRESS = "dcim.macaddress", "MAC address"
    VLAN = "ipam.vlan", "VLAN"
    PREFIX = "ipam.prefix", "Prefix"
    IP_ADDRESS = "ipam.ipaddress", "IP address"


class NetBoxReference(TimestampedModel):
    """A stable NetBox identity attached to one lightweight TekDocs record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="netbox_references")
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT, related_name="netbox_references")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="netbox_references", null=True, blank=True
    )
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="netbox_references")
    object_type = models.CharField(max_length=32, choices=NetBoxObjectType.choices)
    object_id = models.PositiveBigIntegerField()
    observed_fingerprint = models.CharField(max_length=64, blank=True)
    last_observed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("object_type", "object_id", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(object_type__in=NetBoxObjectType.values), name="netbox_type_valid"
            ),
            models.CheckConstraint(condition=models.Q(object_id__gte=1), name="netbox_object_id_positive"),
            models.CheckConstraint(
                condition=models.Q(observed_fingerprint="")
                | models.Q(observed_fingerprint__regex=r"^[0-9a-f]{64}$"),
                name="netbox_fingerprint_valid",
            ),
            models.UniqueConstraint(
                fields=("workspace", "entity"),
                condition=models.Q(archived_at__isnull=True),
                name="netbox_active_entity_unique",
            ),
            models.UniqueConstraint(
                fields=("workspace", "object_type", "object_id"),
                condition=models.Q(archived_at__isnull=True),
                name="netbox_active_remote_unique",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "archived_at"), name="core_netbox_scope_idx"),
            models.Index(fields=("workspace", "object_type", "object_id"), name="core_netbox_remote_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.object_type}:{self.object_id}"

    def clean(self) -> None:
        if self.workspace_id and (
            self.workspace.tenant_id != self.tenant_id
            or self.workspace.organization_id != self.organization_id
        ):
            raise ValidationError("NetBox reference Workspace ownership does not match")
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.workspace_id != self.workspace_id
            or self.entity.organization_id != self.organization_id
            or self.entity.archived_at is not None
        ):
            raise ValidationError("NetBox reference entity must use its active Workspace scope")


class NetworkCircuitKind(models.TextChoices):
    INTERNET = "internet", "Internet"
    WAN = "wan", "WAN"
    MPLS = "mpls", "MPLS"
    DARK_FIBER = "dark_fiber", "Dark fiber"
    BROADBAND = "broadband", "Broadband"
    CELLULAR = "cellular", "Cellular"
    VOICE = "voice", "Voice"
    OTHER = "other", "Other"


class NetworkCircuitStatus(models.TextChoices):
    ORDERED = "ordered", "Ordered"
    PROVISIONING = "provisioning", "Provisioning"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    DISCONNECTED = "disconnected", "Disconnected"


class NetworkCircuit(TimestampedModel):
    """A provider service with exact Workspace ownership and optional contract provenance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_circuits")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_circuits", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_circuit")
    provider = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="provided_network_circuits")
    contract = models.ForeignKey(
        CommercialContract, on_delete=models.PROTECT, related_name="network_circuits", null=True, blank=True
    )
    service_identifier = models.CharField(max_length=240)
    kind = models.CharField(max_length=24, choices=NetworkCircuitKind.choices)
    status = models.CharField(max_length=24, choices=NetworkCircuitStatus.choices)
    bandwidth_down_mbps = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    bandwidth_up_mbps = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    installed_on = models.DateField(null=True, blank=True)
    service_starts_on = models.DateField(null=True, blank=True)
    review_on = models.DateField(null=True, blank=True)
    planned_disconnect_on = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(kind__in=NetworkCircuitKind.values), name="circuit_kind_valid"),
            models.CheckConstraint(
                condition=models.Q(status__in=NetworkCircuitStatus.values), name="circuit_status_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(bandwidth_down_mbps__isnull=True) | models.Q(bandwidth_down_mbps__gt=0),
                name="circuit_down_bandwidth_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(bandwidth_up_mbps__isnull=True) | models.Q(bandwidth_up_mbps__gt=0),
                name="circuit_up_bandwidth_positive",
            ),
            models.UniqueConstraint(
                fields=("tenant", "organization", "provider", "service_identifier"),
                name="circuit_service_id_unique",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "status"), name="core_circuit_scope_idx"),
            models.Index(fields=("tenant", "organization", "provider"), name="core_circuit_provider_idx"),
            models.Index(fields=("tenant", "organization", "review_on"), name="core_circuit_review_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "network_circuit"
        ):
            raise ValidationError("Network circuit entity identity and scope must match")
        if self.provider_id and (self.provider.tenant_id != self.tenant_id or self.provider_id == self.organization_id):
            raise ValidationError("Network circuit provider must be another organization in the same tenant")
        if not self.service_identifier.strip():
            raise ValidationError("Network circuit service identifier is required")
        contract = self.contract if self.contract_id else None
        if contract is not None and (
            contract.tenant_id != self.tenant_id
            or contract.organization_id != self.organization_id
            or contract.provider_id != self.provider_id
            or contract.archived_at is not None
        ):
            raise ValidationError("Network circuit contract must use the same Workspace and provider")
        if (
            self.service_starts_on
            and self.planned_disconnect_on
            and self.planned_disconnect_on < self.service_starts_on
        ):
            raise ValidationError("Circuit disconnect date cannot precede its service start date")


class NetworkHandoffSide(models.TextChoices):
    A = "a", "A side"
    Z = "z", "Z side"


class NetworkHandoffMedia(models.TextChoices):
    COPPER = "copper", "Copper"
    FIBER = "fiber", "Fiber"
    COAX = "coax", "Coax"
    WIRELESS = "wireless", "Wireless"
    VIRTUAL = "virtual", "Virtual"
    OTHER = "other", "Other"


class NetworkCircuitHandoff(TimestampedModel):
    """One physical or logical demarcation for a retained circuit."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="network_circuit_handoffs")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="network_circuit_handoffs", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="network_circuit_handoff")
    circuit = models.ForeignKey(NetworkCircuit, on_delete=models.PROTECT, related_name="handoffs")
    side = models.CharField(max_length=1, choices=NetworkHandoffSide.choices)
    media = models.CharField(max_length=16, choices=NetworkHandoffMedia.choices)
    connector = models.CharField(max_length=120, blank=True)
    provider_reference = models.CharField(max_length=240, blank=True)
    site = models.ForeignKey(
        Site, on_delete=models.PROTECT, related_name="network_circuit_handoffs", null=True, blank=True
    )
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="network_circuit_handoffs", null=True, blank=True
    )
    device = models.ForeignKey(
        NetworkDevice, on_delete=models.PROTECT, related_name="network_circuit_handoffs", null=True, blank=True
    )
    interface = models.ForeignKey(
        NetworkInterface, on_delete=models.PROTECT, related_name="network_circuit_handoffs", null=True, blank=True
    )
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("circuit__entity__display_name", "side", "entity__display_name", "entity_id")
        constraints = [
            models.CheckConstraint(condition=models.Q(side__in=NetworkHandoffSide.values), name="handoff_side_valid"),
            models.CheckConstraint(
                condition=models.Q(media__in=NetworkHandoffMedia.values), name="handoff_media_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(location__isnull=True) | models.Q(site__isnull=False),
                name="handoff_location_requires_site",
            ),
            models.CheckConstraint(
                condition=models.Q(interface__isnull=True) | models.Q(device__isnull=False),
                name="handoff_interface_requires_device",
            ),
            models.UniqueConstraint(fields=("circuit", "side", "entity"), name="handoff_identity_unique"),
            models.UniqueConstraint(
                fields=("interface",),
                condition=models.Q(interface__isnull=False),
                name="handoff_interface_unique",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "circuit"), name="core_handoff_scope_idx"),
            models.Index(fields=("tenant", "organization", "interface"), name="core_handoff_interface_idx"),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "network_circuit_handoff"
        ):
            raise ValidationError("Circuit handoff entity identity and scope must match")
        for related, label in (
            (self.circuit if self.circuit_id else None, "circuit"),
            (self.site if self.site_id else None, "site"),
            (self.location if self.location_id else None, "location"),
            (self.device if self.device_id else None, "device"),
            (self.interface if self.interface_id else None, "interface"),
        ):
            if related is not None and (
                related.tenant_id != self.tenant_id or related.organization_id != self.organization_id
            ):
                raise ValidationError(f"Circuit handoff {label} must use its Workspace scope")
        if self.location_id and self.location is not None and self.location.site_id != self.site_id:
            raise ValidationError("Circuit handoff location must belong to its selected site")
        if self.interface_id and self.interface is not None and self.interface.device_id != self.device_id:
            raise ValidationError("Circuit handoff interface must belong to its selected device")
        if (
            self.device_id
            and self.site_id
            and self.device is not None
            and self.device.site_id not in (None, self.site_id)
        ):
            raise ValidationError("Circuit handoff device placement contradicts its selected site")


class WirelessNetworkPurpose(models.TextChoices):
    CORPORATE = "corporate", "Corporate"
    GUEST = "guest", "Guest"
    IOT = "iot", "IoT"
    VOICE = "voice", "Voice"
    OTHER = "other", "Other"


class WirelessNetworkSecurity(models.TextChoices):
    OPEN = "open", "Open"
    OWE = "owe", "Enhanced open (OWE)"
    WPA2_PERSONAL = "wpa2_personal", "WPA2 Personal"
    WPA3_PERSONAL = "wpa3_personal", "WPA3 Personal"
    WPA2_ENTERPRISE = "wpa2_enterprise", "WPA2 Enterprise"
    WPA3_ENTERPRISE = "wpa3_enterprise", "WPA3 Enterprise"
    MIXED_PERSONAL = "mixed_personal", "WPA2/WPA3 Personal"
    MIXED_ENTERPRISE = "mixed_enterprise", "WPA2/WPA3 Enterprise"


class WirelessNetworkStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"
    RETIRED = "retired", "Retired"


class WirelessNetwork(TimestampedModel):
    """A logical SSID and its non-secret security posture in one exact Workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="wireless_networks")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="wireless_networks", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="wireless_network")
    ssid = models.CharField(max_length=128)
    purpose = models.CharField(max_length=16, choices=WirelessNetworkPurpose.choices)
    security = models.CharField(max_length=32, choices=WirelessNetworkSecurity.choices)
    status = models.CharField(max_length=16, choices=WirelessNetworkStatus.choices)
    hidden = models.BooleanField(default=False)
    client_isolation = models.BooleanField(default=False)
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="wireless_networks", null=True, blank=True)
    vlan = models.ForeignKey(
        NetworkVLAN, on_delete=models.PROTECT, related_name="wireless_networks", null=True, blank=True
    )
    subnet = models.ForeignKey(
        NetworkSubnet, on_delete=models.PROTECT, related_name="wireless_networks", null=True, blank=True
    )
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("ssid", "site_id", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purpose__in=WirelessNetworkPurpose.values), name="wifi_purpose_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(security__in=WirelessNetworkSecurity.values), name="wifi_security_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=WirelessNetworkStatus.values), name="wifi_status_valid"
            ),
            models.UniqueConstraint(
                fields=("tenant", "organization", "site", "ssid"),
                name="wifi_ssid_unique_in_site",
                nulls_distinct=False,
            ),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "status"), name="core_wifi_scope_idx")]

    def __str__(self) -> str:
        return self.ssid

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Wireless network and entity scopes must match")
        if not self.ssid or len(self.ssid.encode("utf-8")) > 32:
            raise ValidationError("SSID must contain between 1 and 32 UTF-8 bytes")
        for related, label in (
            (self.site if self.site_id else None, "site"),
            (self.vlan if self.vlan_id else None, "VLAN"),
            (self.subnet if self.subnet_id else None, "subnet"),
        ):
            if related is not None and (
                related.tenant_id != self.tenant_id or related.organization_id != self.organization_id
            ):
                raise ValidationError(f"Wireless network {label} must use its Workspace scope")
        if self.vlan_id and self.subnet_id and self.subnet is not None and self.subnet.vlan_id != self.vlan_id:
            raise ValidationError("Wireless network subnet must belong to the selected VLAN")


class DNSZone(TimestampedModel):
    """An inventoried DNS zone; TekDocs does not query or serve it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="dns_zones")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="dns_zones", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="dns_zone")
    name = models.CharField(max_length=253)
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("name", "entity_id")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "tenant",
                "organization",
                name="dns_zone_name_unique_in_workspace",
                nulls_distinct=False,
            )
        ]
        indexes = [models.Index(fields=("tenant", "organization", "name"), name="core_dnszone_scope_idx")]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("DNS zone and entity scopes must match")


class DNSRecordType(models.TextChoices):
    A = "A", "A"
    AAAA = "AAAA", "AAAA"
    CNAME = "CNAME", "CNAME"
    MX = "MX", "MX"
    TXT = "TXT", "TXT"
    SRV = "SRV", "SRV"
    CAA = "CAA", "CAA"
    NS = "NS", "NS"
    PTR = "PTR", "PTR"


class DNSRecord(TimestampedModel):
    """A type-validated DNS record protected by the exact Workspace network policy."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="dns_records")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="dns_records", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="dns_record")
    zone = models.ForeignKey(DNSZone, on_delete=models.PROTECT, related_name="records")
    owner_name = models.CharField(max_length=253)
    record_type = models.CharField(max_length=8, choices=DNSRecordType.choices)
    value = models.TextField()
    ttl = models.PositiveIntegerField(default=3600)
    priority = models.PositiveSmallIntegerField(null=True, blank=True)
    weight = models.PositiveSmallIntegerField(null=True, blank=True)
    port = models.PositiveSmallIntegerField(null=True, blank=True)
    ip_address = models.ForeignKey(
        NetworkIPAddress, on_delete=models.PROTECT, related_name="dns_records", null=True, blank=True
    )
    description = models.TextField(blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("zone__name", "owner_name", "record_type", "value", "entity_id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(record_type__in=DNSRecordType.values), name="dns_record_type_valid"
            ),
            models.CheckConstraint(condition=models.Q(ttl__lte=2147483647), name="dns_record_ttl_valid"),
            models.UniqueConstraint(
                fields=("zone", "owner_name", "record_type", "value", "priority", "weight", "port"),
                name="dns_record_value_unique",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=("tenant", "organization", "zone"), name="core_dnsrecord_scope_idx"),
            models.Index(fields=("zone", "owner_name"), name="core_dnsrecord_owner_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.owner_name} {self.record_type}"

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("DNS record and entity scopes must match")
        for related, label in (
            (self.zone if self.zone_id else None, "zone"),
            (self.ip_address if self.ip_address_id else None, "IP address"),
        ):
            if related is not None and (
                related.tenant_id != self.tenant_id or related.organization_id != self.organization_id
            ):
                raise ValidationError(f"DNS record {label} must use its Workspace scope")


class EntityLinkType(models.TextChoices):
    RELATED_TO = "related_to", "Related to"
    CONNECTED_TO = "connected_to", "Connected to"
    DEPENDS_ON = "depends_on", "Depends on"
    MANAGED_BY = "managed_by", "Managed by"
    SUPPLIED_BY = "supplied_by", "Supplied by"
    MANUFACTURED_BY = "manufactured_by", "Manufactured by"
    PARTNERED_WITH = "partnered_with", "Partnered with"
    LOCATED_AT = "located_at", "Located at"
    ASSIGNED_TO = "assigned_to", "Assigned to"
    REFERENCES = "references", "References"


class EntityLink(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="entity_links")
    source = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="outgoing_links")
    target = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="incoming_links")
    link_type = models.CharField(max_length=80, choices=EntityLinkType.choices)
    metadata = models.JSONField(default=dict, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target", "link_type"],
                condition=models.Q(archived_at__isnull=True),
                name="unique_active_typed_entity_link",
            ),
            models.CheckConstraint(condition=~models.Q(source=models.F("target")), name="entity_link_not_self"),
            models.CheckConstraint(
                condition=models.Q(link_type__in=EntityLinkType.values),
                name="entity_link_type_supported",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "link_type", "archived_at"], name="entity_link_type_active_idx"),
            models.Index(fields=["tenant", "source", "archived_at"], name="entity_link_source_active_idx"),
            models.Index(fields=["tenant", "target", "archived_at"], name="entity_link_target_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source_id} {self.link_type} {self.target_id}"

    def clean(self) -> None:
        if self.source_id and self.tenant_id != self.source.tenant_id:
            raise ValidationError("Source entity must belong to the link tenant")
        if self.target_id and self.tenant_id != self.target.tenant_id:
            raise ValidationError("Target entity must belong to the link tenant")
        if self.metadata != {}:
            raise ValidationError("Entity-link metadata is not accepted by this release")


class DocumentCategory(models.TextChoices):
    GENERAL = "general", "General"
    POLICY = "policy", "Policy"
    PROCEDURE = "procedure", "Procedure"
    GUIDE = "guide", "Guide"
    REFERENCE = "reference", "Reference"


class Document(TimestampedModel):
    """A Markdown document owned by exactly one MSP or organization workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="documents")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="documents", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="document_record")
    category = models.CharField(
        max_length=20,
        choices=DocumentCategory.choices,
        default=DocumentCategory.GENERAL,
    )
    is_template = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(category__in=DocumentCategory.values),
                name="document_category_supported",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "organization", "archived_at"]),
            models.Index(
                fields=["tenant", "organization", "category", "is_template", "archived_at"],
                name="core_doc_category_template_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.entity.display_name

    def clean(self) -> None:
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Document entity must use the document workspace scope")


def document_attachment_upload_to(instance: "DocumentAttachment", _filename: str) -> str:
    """Return an opaque storage key that never includes an authored filename."""

    return str(
        PurePosixPath("document-attachments") / str(instance.tenant_id) / str(instance.document_id) / str(instance.id)
    )


def publication_artifact_upload_to(instance: "DocumentPublicationArtifact", _filename: str) -> str:
    """Return an opaque retained-artifact key without authored path material."""

    return str(
        PurePosixPath("publication-artifacts")
        / str(instance.tenant_id)
        / str(instance.publication_id)
        / str(instance.id)
    )


class DocumentAttachment(TimestampedModel):
    """A private managed file owned by exactly one document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_attachments")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="document_attachments",
        null=True,
        blank=True,
    )
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="attachments")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="document_attachment_record")
    file = models.FileField(upload_to=document_attachment_upload_to, max_length=500)
    original_filename = models.CharField(max_length=240)
    media_type = models.CharField(max_length=120)
    size = models.PositiveBigIntegerField()
    checksum = models.CharField(max_length=64)
    storage_provider = models.CharField(max_length=80, default="django-default")
    scan_status = models.CharField(max_length=20, default="clean")
    scan_engine = models.CharField(max_length=120, default="legacy-validation")
    scanned_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="document_attachments",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(scan_status="clean"), name="document_attachment_clean_only"),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "organization", "document", "archived_at"],
                name="core_docatt_scope_idx",
            ),
            models.Index(fields=["document", "checksum"], name="core_docatt_checksum_idx"),
        ]

    def __str__(self) -> str:
        return self.original_filename

    def clean(self) -> None:
        if self.document_id and (
            self.document.tenant_id != self.tenant_id or self.document.organization_id != self.organization_id
        ):
            raise ValidationError("Attachment must use its document workspace scope")
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Attachment entity must use the attachment workspace scope")
        if self.scan_status != "clean" or not self.scan_engine or not self.storage_provider or not self.scanned_at:
            raise ValidationError("Only clean, scanned attachments may enter managed storage")


class PublicationAudience(models.TextChoices):
    MSP_INTERNAL = "msp_internal", "MSP internal"
    CLIENT_VISIBLE = "client_visible", "Client visible"


class PublicationRetention(models.TextChoices):
    PERMANENT = "permanent", "Permanent"
    REVIEW_ON = "review_on", "Review on date"


class PublicationArtifactKind(models.TextChoices):
    PDF = "pdf", "PDF"
    ATTACHMENT = "attachment", "Retained attachment"


class PublicationControlAction(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    WITHDRAWN = "withdrawn", "Withdrawn"


class DocumentPublication(models.Model):
    """An append-only STATIC snapshot of one document and its resolved dependencies."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_publications")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="document_publications",
        null=True,
        blank=True,
    )
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="publications")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="document_publication_record")
    title = models.CharField(max_length=240)
    category = models.CharField(max_length=20, choices=DocumentCategory.choices)
    reason = models.CharField(max_length=500)
    audience = models.CharField(max_length=24, choices=PublicationAudience.choices)
    retention = models.CharField(max_length=20, choices=PublicationRetention.choices)
    retention_review_on = models.DateField(null=True, blank=True)
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="successors",
        null=True,
        blank=True,
    )
    canonical_markdown = models.TextField(blank=True)
    sanitized_html = models.TextField(blank=True)
    manifest = models.JSONField()
    content_digest = models.CharField(max_length=64)
    signature = models.TextField()
    signature_algorithm = models.CharField(max_length=20, default="Ed25519")
    public_key = models.TextField()
    key_fingerprint = models.CharField(max_length=64)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="document_publications",
        null=True,
        blank=True,
    )
    published_at = models.DateTimeField()

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-published_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(audience__in=PublicationAudience.values), name="publication_audience_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(retention__in=PublicationRetention.values), name="publication_retention_valid"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(retention=PublicationRetention.PERMANENT, retention_review_on__isnull=True)
                    | models.Q(retention=PublicationRetention.REVIEW_ON, retention_review_on__isnull=False)
                ),
                name="publication_retention_date_valid",
            ),
            models.CheckConstraint(
                condition=(models.Q(audience=PublicationAudience.MSP_INTERNAL) | models.Q(organization__isnull=False)),
                name="publication_client_audience_scoped",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "organization", "document", "published_at"],
                name="core_docpub_scope_idx",
            ),
            models.Index(fields=["document", "content_digest"], name="core_docpub_digest_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} — {self.published_at.isoformat()}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Document publications are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Document publications are append-only")

    def clean(self) -> None:
        if self.document_id and (
            self.document.tenant_id != self.tenant_id or self.document.organization_id != self.organization_id
        ):
            raise ValidationError("Publication must use its source document workspace scope")
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id or self.entity.organization_id != self.organization_id
        ):
            raise ValidationError("Publication entity must use the publication workspace scope")
        if self.entity_id and self.entity.entity_type != "document_publication":
            raise ValidationError("Publication entity must use the document_publication type")
        if not isinstance(self.manifest, dict) or self.manifest.get("format") not in {
            "tekdocs-static-publication/v1",
            "tekdocs-static-publication/v2",
        }:
            raise ValidationError("Publication manifest format is invalid")
        expected_identity = {
            "publication_id": str(self.id),
            "publication_entity_id": str(self.entity_id),
            "source_document_id": str(self.document.entity_id) if self.document_id else "",
        }
        if any(self.manifest.get(key) != value for key, value in expected_identity.items()):
            raise ValidationError("Publication manifest identity does not match the publication")
        workspace = self.manifest.get("workspace")
        organization = self.organization if self.organization_id else None
        expected_workspace = {
            "kind": "organization" if self.organization_id else "msp",
            "id": str(organization.entity_id) if organization is not None else None,
        }
        if workspace != expected_workspace:
            raise ValidationError("Publication manifest workspace does not match the publication")
        if not self.reason.strip() or len(self.reason) > 500:
            raise ValidationError("Publication reason is required and may not exceed 500 characters")
        if self.audience == PublicationAudience.CLIENT_VISIBLE and self.organization_id is None:
            raise ValidationError("Client-visible publications require an organization workspace")
        if (self.retention == PublicationRetention.REVIEW_ON) != (self.retention_review_on is not None):
            raise ValidationError("Publication retention date does not match its retention class")
        supersedes = self.supersedes if self.supersedes_id else None
        if supersedes is not None and (
            supersedes.tenant_id != self.tenant_id
            or supersedes.organization_id != self.organization_id
            or supersedes.document_id != self.document_id
            or supersedes.audience != self.audience
        ):
            raise ValidationError("A correction may supersede only a publication of the same document and workspace")
        if self.manifest.get("format") == "tekdocs-static-publication/v2":
            expected_lifecycle = {
                "reason": self.reason,
                "audience": self.audience,
                "retention": self.retention,
                "retention_review_on": self.retention_review_on.isoformat() if self.retention_review_on else None,
                "supersedes_id": str(supersedes.entity_id) if supersedes is not None else None,
            }
            if any(self.manifest.get(key) != value for key, value in expected_lifecycle.items()):
                raise ValidationError("Publication manifest lifecycle metadata does not match the publication")

    @property
    def lifecycle_state(self) -> str:
        actions = self.control_actions
        if PublicationControlAction.WITHDRAWN in actions:
            return "withdrawn"
        if PublicationControlAction.APPROVED not in actions:
            return "pending_approval"
        successors = list(getattr(self, "prefetched_successors", ()))
        if not successors:
            successors = list(self.successors.all())
        if any(PublicationControlAction.APPROVED in successor.control_actions for successor in successors):
            return "superseded"
        if self.retention_review_on is not None and self.retention_review_on <= timezone.localdate():
            return "review_due"
        return "published"

    @property
    def control_actions(self) -> frozenset[str]:
        events = list(getattr(self, "prefetched_control_events", ()))
        if not events:
            events = list(self.control_events.all())
        return frozenset(event.action for event in events)

    @property
    def superseded_by_publication(self) -> "DocumentPublication | None":
        successors = list(getattr(self, "prefetched_successors", ()))
        if not successors:
            successors = list(self.successors.all())
        return next(
            (
                successor
                for successor in successors
                if PublicationControlAction.APPROVED in successor.control_actions
            ),
            None,
        )


class DocumentPublicationControlEvent(models.Model):
    """An append-only distribution decision for one immutable STATIC publication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_publication_events")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="document_publication_events",
        null=True,
        blank=True,
    )
    publication = models.ForeignKey(
        DocumentPublication,
        on_delete=models.PROTECT,
        related_name="control_events",
    )
    action = models.CharField(max_length=20, choices=PublicationControlAction.choices)
    reason = models.CharField(max_length=500)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="document_publication_control_events",
        null=True,
        blank=True,
    )
    occurred_at = models.DateTimeField(default=timezone.now)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("occurred_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(action__in=PublicationControlAction.values),
                name="publication_control_action_valid",
            ),
            models.UniqueConstraint(
                fields=("publication", "action"),
                name="unique_publication_control_action",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant", "organization", "publication", "occurred_at"),
                name="core_pubctl_scope_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.publication_id}: {self.action}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Publication control events are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Publication control events are append-only")

    def clean(self) -> None:
        if self.publication_id and (
            self.publication.tenant_id != self.tenant_id
            or self.publication.organization_id != self.organization_id
        ):
            raise ValidationError("Publication control event must use its publication workspace scope")
        if not self.reason.strip() or len(self.reason) > 500:
            raise ValidationError("Publication control reason is required and may not exceed 500 characters")


class DocumentPublicationArtifact(models.Model):
    """An append-only retained byte artifact belonging to a STATIC publication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_publication_artifacts")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="document_publication_artifacts",
        null=True,
        blank=True,
    )
    publication = models.ForeignKey(DocumentPublication, on_delete=models.PROTECT, related_name="artifacts")
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="document_publication_artifact")
    kind = models.CharField(max_length=20, choices=PublicationArtifactKind.choices)
    source_attachment = models.ForeignKey(
        DocumentAttachment,
        on_delete=models.PROTECT,
        related_name="publication_artifacts",
        null=True,
        blank=True,
    )
    file = models.FileField(upload_to=publication_artifact_upload_to, max_length=500)
    original_filename = models.CharField(max_length=240)
    media_type = models.CharField(max_length=120)
    size = models.PositiveBigIntegerField()
    checksum = models.CharField(max_length=64)
    created_at = models.DateTimeField()

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("kind", "original_filename", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=PublicationArtifactKind.values), name="publication_artifact_kind_valid"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(kind=PublicationArtifactKind.PDF, source_attachment__isnull=True)
                    | models.Q(kind=PublicationArtifactKind.ATTACHMENT, source_attachment__isnull=False)
                ),
                name="publication_artifact_source_valid",
            ),
            models.UniqueConstraint(
                fields=("publication", "kind"),
                condition=models.Q(kind=PublicationArtifactKind.PDF),
                name="one_pdf_per_publication",
            ),
            models.UniqueConstraint(
                fields=("publication", "source_attachment"),
                condition=models.Q(source_attachment__isnull=False),
                name="one_retained_source_attachment",
            ),
        ]
        indexes = [models.Index(fields=("tenant", "organization", "publication"), name="core_pubart_scope_idx")]

    def __str__(self) -> str:
        return f"{self.publication.title}: {self.original_filename}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Publication artifacts are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Publication artifacts are append-only")

    def clean(self) -> None:
        if self.publication_id and (
            self.publication.tenant_id != self.tenant_id or self.publication.organization_id != self.organization_id
        ):
            raise ValidationError("Publication artifact must use its publication workspace scope")
        if self.entity_id and (
            self.entity.tenant_id != self.tenant_id
            or self.entity.organization_id != self.organization_id
            or self.entity.entity_type != "document_publication_artifact"
        ):
            raise ValidationError("Publication artifact entity scope or type is invalid")
        if self.kind == PublicationArtifactKind.PDF and self.source_attachment_id is not None:
            raise ValidationError("PDF artifacts cannot identify a source attachment")
        if self.kind == PublicationArtifactKind.ATTACHMENT and self.source_attachment_id is None:
            raise ValidationError("Retained attachment artifacts require a source attachment")
        source_attachment = self.source_attachment if self.source_attachment_id else None
        if source_attachment is not None and source_attachment.document_id != self.publication.document_id:
            raise ValidationError("Retained attachment must belong to the source document")


class Block(TimestampedModel):
    """A stable addressable content block whose content is an immutable revision chain."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="blocks")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="blocks", null=True, blank=True
    )
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="block_record")
    current_revision = models.ForeignKey(
        "BlockRevision",
        on_delete=models.PROTECT,
        related_name="current_for_blocks",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        indexes = [models.Index(fields=["tenant", "organization", "archived_at"])]

    def __str__(self) -> str:
        return str(self.entity_id)


class BlockRevision(models.Model):
    """Append-only canonical Markdown for one stable block."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="block_revisions")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="block_revisions", null=True, blank=True
    )
    block = models.ForeignKey(Block, on_delete=models.PROTECT, related_name="revisions")
    parent = models.ForeignKey("self", on_delete=models.PROTECT, related_name="children", null=True, blank=True)
    revision_number = models.PositiveIntegerField()
    markdown = models.TextField(blank=True)
    checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="block_revisions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("-revision_number", "-created_at", "id")
        constraints = [
            models.UniqueConstraint(fields=["block", "revision_number"], name="unique_block_revision_number"),
            models.CheckConstraint(condition=models.Q(revision_number__gte=1), name="block_revision_number_positive"),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "organization", "block", "-revision_number"],
                name="core_blockr_tenant__42e5a8_idx",
            ),
            models.Index(fields=["block", "checksum"], name="core_blockr_block_i_a9954b_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.block_id} revision {self.revision_number}"

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._state.adding is False:
            raise ValidationError("Block revisions are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValidationError("Block revisions are append-only")


class PlacementResolutionMode(models.TextChoices):
    LIVE = "live", "Live"
    PINNED = "pinned", "Pinned"


class DocumentPlacement(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="document_placements")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="document_placements", null=True, blank=True
    )
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="placements")
    block = models.ForeignKey(Block, on_delete=models.PROTECT, related_name="placements")
    parent = models.ForeignKey("self", on_delete=models.PROTECT, related_name="children", null=True, blank=True)
    position = models.PositiveIntegerField()
    resolution_mode = models.CharField(
        max_length=12,
        choices=PlacementResolutionMode.choices,
        default=PlacementResolutionMode.LIVE,
    )
    pinned_revision = models.ForeignKey(
        BlockRevision,
        on_delete=models.PROTECT,
        related_name="pinned_placements",
        null=True,
        blank=True,
    )

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["document", "position"],
                condition=models.Q(parent__isnull=True),
                name="unique_document_root_position",
            ),
            models.UniqueConstraint(
                fields=["parent", "position"],
                condition=models.Q(parent__isnull=False),
                name="unique_document_child_position",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(resolution_mode=PlacementResolutionMode.LIVE, pinned_revision__isnull=True)
                    | models.Q(resolution_mode=PlacementResolutionMode.PINNED, pinned_revision__isnull=False)
                ),
                name="document_placement_resolution_target",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "organization", "document", "parent", "position"],
                name="core_docpl_scope_tree_idx",
            ),
            models.Index(
                fields=["tenant", "block", "resolution_mode"],
                name="core_docpl_block_mode_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} position {self.position}"

    def clean(self) -> None:
        if self.document_id and (
            self.document.tenant_id != self.tenant_id or self.document.organization_id != self.organization_id
        ):
            raise ValidationError("Placement must use its document workspace scope")
        if self.block_id and self.block.tenant_id != self.tenant_id:
            raise ValidationError("Placed block must belong to the placement tenant")
        parent = self.parent if self.parent_id else None
        if parent is not None and (
            parent.document_id != self.document_id
            or parent.tenant_id != self.tenant_id
            or parent.organization_id != self.organization_id
        ):
            raise ValidationError("Placement parent must belong to the same document")
        if self.resolution_mode == PlacementResolutionMode.LIVE and self.pinned_revision_id is not None:
            raise ValidationError("Live placements cannot pin a revision")
        if self.resolution_mode == PlacementResolutionMode.PINNED and self.pinned_revision_id is None:
            raise ValidationError("Pinned placements require a revision")
        pinned_revision = self.pinned_revision if self.pinned_revision_id else None
        if pinned_revision is not None and pinned_revision.block_id != self.block_id:
            raise ValidationError("Pinned revision must belong to the placed block")


class DocumentationListingReference(TimestampedModel):
    """Projects an MSP-owned document into one client documentation index."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="documentation_references")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="documentation_references")
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="listing_references")
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "document"],
                condition=models.Q(archived_at__isnull=True),
                name="unique_active_documentation_listing_reference",
            )
        ]
        indexes = [models.Index(fields=["tenant", "organization", "archived_at"])]

    def __str__(self) -> str:
        return f"{self.document_id} listed in {self.organization_id}"


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="audit_events", null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=120)
    entity_id = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = models.Manager()
    scoped = TenantScopedManager()

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
