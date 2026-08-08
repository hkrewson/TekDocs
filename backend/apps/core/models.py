import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .scoping import OrganizationScopedManager, TenantScopedManager


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
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.PROTECT,
        related_name="scoped_entities",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    scoped = OrganizationScopedManager()

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "entity_type"]),
            models.Index(fields=["tenant", "display_name"]),
            models.Index(fields=["tenant", "organization", "entity_type"]),
        ]

    def __str__(self) -> str:
        return self.display_name

    def clean(self) -> None:
        organization = self.organization if self.organization_id else None
        if organization is not None and self.tenant_id != organization.tenant_id:
            raise ValidationError("Organization scope must belong to the entity tenant")


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


class EntityLinkType(models.TextChoices):
    RELATED_TO = "related_to", "Related to"
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
