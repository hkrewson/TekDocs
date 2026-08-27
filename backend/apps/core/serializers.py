from typing import cast
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .document_attachments import resolve_rendered_attachments
from .document_key_freeze import expand_rendered_content_keys
from .document_key_resolution import resolve_rendered_keys
from .documents import ResolvedDocument, ResolvedPlacement, resolve_document
from .entity_mentions import resolve_entity_mentions
from .models import (
    Block,
    BlockKind,
    BlockRevision,
    Document,
    DocumentAttachment,
    DocumentAttachmentPurpose,
    DocumentCategory,
    DocumentPlacement,
    DocumentPublication,
    DocumentPublicationControlEvent,
    LocationKind,
    Organization,
    OrganizationAccessMode,
    OrganizationKind,
    PersonAssociationKind,
    PlacementResolutionMode,
    PublicationAudience,
    PublicationRetention,
    Site,
)
from .relationships import SEARCHABLE_ENTITY_TYPES
from .rendering import render_markdown


def _clean_name(value: str) -> str:
    if any(ord(character) < 32 for character in value):
        raise serializers.ValidationError("Name cannot contain control characters.")
    return value


class OrganizationWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    legal_name = serializers.CharField(max_length=240, trim_whitespace=True, required=False, allow_blank=True)
    website = serializers.URLField(max_length=500, required=False, allow_blank=True)
    classifications = serializers.ListField(
        child=serializers.ChoiceField(choices=OrganizationKind.choices),
        min_length=1,
        max_length=len(OrganizationKind),
        allow_empty=False,
    )

    def validate_classifications(self, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Classifications must be unique.")
        return value

    def validate_website(self, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"}:
            raise serializers.ValidationError("Website must use HTTP or HTTPS.")
        if parsed.username is not None or parsed.password is not None:
            raise serializers.ValidationError("Website must not contain embedded credentials.")
        return value


class OrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    legal_name = serializers.CharField()
    website = serializers.URLField()
    access_mode = serializers.ChoiceField(choices=OrganizationAccessMode.choices)
    classifications = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_classifications(self, organization: Organization) -> list[str]:
        return sorted(classification.kind for classification in organization.classifications.all())


class WorkspaceContextSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("msp", "organization"))
    id = serializers.UUIDField()
    name = serializers.CharField()
    classifications = serializers.ListField(child=serializers.ChoiceField(choices=OrganizationKind.choices))
    capabilities = serializers.ListField(child=serializers.CharField())
    organization = OrganizationSerializer(allow_null=True)


class WorkspaceSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")
    classification = serializers.ChoiceField(
        choices=OrganizationKind.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    page = serializers.IntegerField(min_value=1, max_value=100, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=25, required=False, default=15)


class WorkspaceOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    classifications = serializers.ListField(child=serializers.ChoiceField(choices=OrganizationKind.choices))
    capabilities = serializers.ListField(child=serializers.CharField())


class WorkspaceSearchResultSerializer(serializers.Serializer):
    results = WorkspaceOptionSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()


class LocationWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    kind = serializers.ChoiceField(choices=LocationKind.choices)
    code = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        for field in ("code",):
            value = attrs.get(field)
            if isinstance(value, str) and any(ord(character) < 32 for character in value):
                raise serializers.ValidationError({field: "Control characters are not allowed."})
        return attrs


class LocationSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    site_id = serializers.UUIDField(source="site.entity_id")
    parent_id = serializers.UUIDField(source="parent.entity_id", allow_null=True)
    name = serializers.CharField(source="entity.display_name")
    kind = serializers.ChoiceField(choices=LocationKind.choices)
    code = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class SiteWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    code = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)
    address_line_1 = serializers.CharField(max_length=240, required=False, allow_blank=True, trim_whitespace=True)
    address_line_2 = serializers.CharField(max_length=240, required=False, allow_blank=True, trim_whitespace=True)
    city = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    region = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    postal_code = serializers.CharField(max_length=32, required=False, allow_blank=True, trim_whitespace=True)
    country_code = serializers.RegexField(
        r"^[A-Za-z]{2}$",
        max_length=2,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    timezone = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        for field, value in attrs.items():
            if isinstance(value, str) and any(ord(character) < 32 for character in value):
                raise serializers.ValidationError({field: "Control characters are not allowed."})
        if "country_code" in attrs:
            attrs["country_code"] = attrs["country_code"].upper()
        timezone = attrs.get("timezone", "")
        if timezone:
            try:
                ZoneInfo(timezone)
            except ZoneInfoNotFoundError as exc:
                raise serializers.ValidationError({"timezone": "Use a valid IANA timezone name."}) from exc
        return attrs


class SiteSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    organization_id = serializers.UUIDField(source="organization.entity_id", allow_null=True)
    name = serializers.CharField(source="entity.display_name")
    code = serializers.CharField()
    address_line_1 = serializers.CharField()
    address_line_2 = serializers.CharField()
    city = serializers.CharField()
    region = serializers.CharField()
    postal_code = serializers.CharField()
    country_code = serializers.CharField()
    timezone = serializers.CharField()
    phone = serializers.CharField()
    locations = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    @extend_schema_field(LocationSerializer(many=True))
    def get_locations(self, site: Site) -> list[dict[str, object]]:
        records = getattr(site, "active_locations", ())
        return cast(list[dict[str, object]], LocationSerializer(records, many=True).data)


class SiteQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")


class SiteResultSerializer(serializers.Serializer):
    results = SiteSerializer(many=True)
    count = serializers.IntegerField()


PERSON_SORT_FIELDS = (
    "full_name",
    "preferred_name",
    "kind",
    "role",
    "responsibility",
    "location",
    "office",
    "phone",
    "email",
)
PERSON_FILTER_FIELDS = PERSON_SORT_FIELDS[1:]


class PersonWriteSerializer(serializers.Serializer):
    full_name = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    preferred_name = serializers.CharField(max_length=160, required=False, allow_blank=True, trim_whitespace=True)
    kind = serializers.ChoiceField(choices=PersonAssociationKind.choices)
    role = serializers.CharField(max_length=160, required=False, allow_blank=True, trim_whitespace=True)
    responsibility = serializers.CharField(max_length=240, required=False, allow_blank=True, trim_whitespace=True)
    location = serializers.CharField(max_length=160, required=False, allow_blank=True, trim_whitespace=True)
    office = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    site_id = serializers.UUIDField(required=False, allow_null=True)
    structured_location_id = serializers.UUIDField(required=False, allow_null=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        for field, value in attrs.items():
            if isinstance(value, str) and any(ord(character) < 32 for character in value):
                raise serializers.ValidationError({field: "Control characters are not allowed."})
        return attrs


class PersonSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="person.entity_id")
    association_id = serializers.UUIDField(source="id")
    organization_id = serializers.UUIDField(source="organization.entity_id", allow_null=True)
    full_name = serializers.CharField(source="person.entity.display_name")
    preferred_name = serializers.CharField(source="person.preferred_name")
    kind = serializers.ChoiceField(choices=PersonAssociationKind.choices)
    role = serializers.CharField()
    responsibility = serializers.CharField()
    location = serializers.CharField()
    office = serializers.CharField()
    site_id = serializers.UUIDField(source="site.entity_id", allow_null=True)
    structured_location_id = serializers.UUIDField(source="structured_location.entity_id", allow_null=True)
    phone = serializers.CharField(source="person.phone")
    email = serializers.EmailField(source="person.email")
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class PeopleQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")
    filter_field = serializers.ChoiceField(
        choices=PERSON_FILTER_FIELDS,
        required=False,
        allow_blank=True,
        default="",
    )
    filter_value = serializers.CharField(
        max_length=80,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )
    ordering = serializers.ChoiceField(
        choices=tuple(PERSON_SORT_FIELDS) + tuple(f"-{field}" for field in PERSON_SORT_FIELDS),
        required=False,
        default="full_name",
    )
    page = serializers.IntegerField(min_value=1, max_value=1000, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=50, required=False, default=25)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if bool(attrs["filter_field"]) != bool(attrs["filter_value"]):
            raise serializers.ValidationError("Filter field and value must be supplied together.")
        return attrs


class PeopleResultSerializer(serializers.Serializer):
    results = PersonSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()


class DocumentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    markdown = serializers.CharField(required=False, allow_blank=True, max_length=1_000_000, trim_whitespace=False)
    category = serializers.ChoiceField(
        choices=DocumentCategory.choices,
        required=False,
        default=DocumentCategory.GENERAL,
    )
    is_template = serializers.BooleanField(required=False, default=False)
    library_visible = serializers.BooleanField(required=False, default=False)


class FileBackedDocumentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1_000_000, trim_whitespace=False)
    category = serializers.ChoiceField(
        choices=DocumentCategory.choices,
        required=False,
        default=DocumentCategory.GENERAL,
    )
    file = serializers.FileField()

    def validate_notes(self, value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n")


class DocumentUpdateSerializer(DocumentCreateSerializer):
    base_revision_id = serializers.UUIDField()


class DocumentRestructureApplySerializer(serializers.Serializer):
    base_revision_id = serializers.UUIDField()


class DocumentRestructureNoticeSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()


class DocumentRestructureSectionSerializer(serializers.Serializer):
    position = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=BlockKind.choices)
    name = serializers.CharField()
    markdown = serializers.CharField(allow_blank=True)
    checksum = serializers.CharField()


class DocumentRestructureDependenciesSerializer(serializers.Serializer):
    publication_count = serializers.IntegerField()
    attachment_count = serializers.IntegerField()
    template_managed = serializers.BooleanField()
    remote_managed = serializers.BooleanField()
    shared_placement_count = serializers.IntegerField()


class DocumentRestructurePreviewSerializer(serializers.Serializer):
    eligible = serializers.BooleanField()
    base_revision_id = serializers.UUIDField(allow_null=True)
    base_checksum = serializers.CharField(allow_blank=True)
    section_count = serializers.IntegerField()
    sections = DocumentRestructureSectionSerializer(many=True)
    blockers = DocumentRestructureNoticeSerializer(many=True)
    warnings = DocumentRestructureNoticeSerializer(many=True)
    dependencies = DocumentRestructureDependenciesSerializer()


class DocumentListQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True, default="")
    category = serializers.ChoiceField(
        choices=DocumentCategory.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    template = serializers.ChoiceField(
        choices=("all", "documents", "templates"),
        required=False,
        default="all",
    )


class DocumentTemplateInstantiateSerializer(serializers.Serializer):
    source_document_id = serializers.UUIDField()
    title = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    category = serializers.ChoiceField(choices=DocumentCategory.choices)
    placement_rules = serializers.DictField(
        child=serializers.ChoiceField(choices=("copy", "live", "pinned")),
        required=False,
        default=dict,
    )


class DocumentTemplateRolloutPreviewSerializer(serializers.Serializer):
    enrollment_id = serializers.UUIDField()


class DocumentTemplateRolloutApplySerializer(serializers.Serializer):
    enrollment_id = serializers.UUIDField()
    expected_applied_revision_id = serializers.UUIDField()
    placement_rules = serializers.DictField(
        child=serializers.ChoiceField(choices=("copy", "live", "pinned")),
        required=False,
        default=dict,
    )


class DocumentTemplateRolloutResultSerializer(serializers.Serializer):
    enrollment_id = serializers.UUIDField()
    applied_revision_id = serializers.UUIDField()
    current_revision = serializers.IntegerField()
    available_revision = serializers.IntegerField()
    up_to_date = serializers.BooleanField()
    added = serializers.ListField(child=serializers.DictField())
    changed = serializers.ListField(child=serializers.DictField())
    removed = serializers.ListField(child=serializers.DictField())
    conflicts = serializers.ListField(child=serializers.DictField())


class MarkdownImportSerializer(serializers.Serializer):
    file = serializers.FileField()
    title = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    category = serializers.ChoiceField(choices=DocumentCategory.choices, default=DocumentCategory.GENERAL)
    is_template = serializers.BooleanField(default=False)


class DocumentAttachmentWriteSerializer(serializers.Serializer):
    file = serializers.FileField()


class DocumentAttachmentSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    filename = serializers.CharField(source="original_filename")
    media_type = serializers.CharField()
    size = serializers.IntegerField()
    checksum = serializers.CharField()
    scan_status = serializers.CharField()
    scan_engine = serializers.CharField()
    scanned_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()


class DocumentPrimaryFileSerializer(DocumentAttachmentSerializer):
    version_number = serializers.IntegerField()
    replaces_id = serializers.UUIDField(source="replaces.entity_id", allow_null=True)
    is_current = serializers.BooleanField()


class PublicationVerificationSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    digest_valid = serializers.BooleanField()
    signature_valid = serializers.BooleanField()
    key_fingerprint_valid = serializers.BooleanField()
    trusted_key = serializers.BooleanField()


class DocumentPublicationWriteSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=1, max_length=500, trim_whitespace=True)
    audience = serializers.ChoiceField(choices=PublicationAudience.choices)
    retention = serializers.ChoiceField(choices=PublicationRetention.choices)
    retention_review_on = serializers.DateField(required=False, allow_null=True)
    supersedes_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_reason(self, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise serializers.ValidationError("Control characters are not allowed.")
        return value

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        review_on = attrs.get("retention_review_on")
        if (attrs["retention"] == PublicationRetention.REVIEW_ON) != (review_on is not None):
            raise serializers.ValidationError(
                {"retention_review_on": "A review date is required only for review-on-date retention."}
            )
        if review_on is not None and review_on < timezone.localdate():
            raise serializers.ValidationError(
                {"retention_review_on": "The retention review date cannot be in the past."}
            )
        if attrs["audience"] == PublicationAudience.CLIENT_VISIBLE and not self.context.get("organization_scoped"):
            raise serializers.ValidationError(
                {"audience": "Client-visible publications require an organization workspace."}
            )
        return attrs


class DocumentPublicationControlWriteSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=1, max_length=500, trim_whitespace=True)

    def validate_reason(self, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise serializers.ValidationError("Control characters are not allowed.")
        return value


class DocumentPublicationControlEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    action = serializers.CharField()
    reason = serializers.CharField()
    actor = serializers.SerializerMethodField()
    occurred_at = serializers.DateTimeField()

    def get_actor(self, obj: DocumentPublicationControlEvent) -> str | None:
        if obj.actor is None:
            return None
        return obj.actor.get_full_name() or obj.actor.get_username()


class PublicationAudienceProjectionSerializer(serializers.Serializer):
    audience = serializers.CharField()
    available = serializers.BooleanField()
    state = serializers.CharField()


class DocumentPublicationArtifactSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    kind = serializers.CharField()
    filename = serializers.CharField(source="original_filename")
    media_type = serializers.CharField()
    size = serializers.IntegerField()
    checksum = serializers.CharField()
    source_attachment_id = serializers.UUIDField(source="source_attachment.entity_id", allow_null=True)


class DocumentPublicationSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    source_document_id = serializers.UUIDField(source="document.entity_id")
    title = serializers.CharField()
    category = serializers.ChoiceField(choices=DocumentCategory.choices)
    reason = serializers.CharField()
    audience = serializers.ChoiceField(choices=PublicationAudience.choices)
    retention = serializers.ChoiceField(choices=PublicationRetention.choices)
    retention_review_on = serializers.DateField(allow_null=True)
    lifecycle_state = serializers.CharField()
    supersedes_id = serializers.UUIDField(source="supersedes.entity_id", allow_null=True)
    superseded_by_id = serializers.SerializerMethodField()
    control_events = DocumentPublicationControlEventSerializer(many=True)
    audience_projections = serializers.SerializerMethodField()
    artifacts = DocumentPublicationArtifactSerializer(many=True)
    content_digest = serializers.CharField()
    signature_algorithm = serializers.CharField()
    signature = serializers.CharField()
    public_key = serializers.CharField()
    key_fingerprint = serializers.CharField()
    published_by = serializers.SerializerMethodField()
    published_at = serializers.DateTimeField()
    verification = serializers.SerializerMethodField()

    def get_superseded_by_id(self, obj: DocumentPublication) -> UUID | None:
        successor = obj.superseded_by_publication
        return successor.entity_id if successor is not None else None

    @extend_schema_field(PublicationAudienceProjectionSerializer(many=True))
    def get_audience_projections(self, obj: DocumentPublication) -> list[dict[str, object]]:
        state = obj.lifecycle_state
        if obj.audience == PublicationAudience.MSP_INTERNAL:
            client_state = "not_intended"
        elif state in {"published", "review_due"}:
            client_state = "available"
        else:
            client_state = state
        return [
            {"audience": "msp_staff", "available": True, "state": "retained"},
            {"audience": "client_portal", "available": client_state == "available", "state": client_state},
        ]

    def get_published_by(self, obj: DocumentPublication) -> str | None:
        if obj.published_by is None:
            return None
        return obj.published_by.get_full_name() or obj.published_by.get_username()

    @extend_schema_field(PublicationVerificationSerializer)
    def get_verification(self, obj: DocumentPublication) -> dict[str, bool]:
        from .publications import verify_publication

        return verify_publication(obj)


class DocumentPublicationDetailSerializer(DocumentPublicationSerializer):
    canonical_markdown = serializers.CharField(allow_blank=True)
    sanitized_html = serializers.CharField(allow_blank=True)
    manifest = serializers.JSONField()


class PortalDocumentArtifactSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    kind = serializers.CharField()
    filename = serializers.CharField(source="original_filename")
    size = serializers.IntegerField()
    checksum = serializers.CharField()


class PortalDocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    title = serializers.CharField()
    category = serializers.ChoiceField(choices=DocumentCategory.choices)
    reason = serializers.CharField()
    lifecycle_state = serializers.SerializerMethodField()
    retention = serializers.ChoiceField(choices=PublicationRetention.choices)
    retention_review_on = serializers.DateField(allow_null=True)
    published_at = serializers.DateTimeField()
    content_digest = serializers.CharField()
    source_kind = serializers.SerializerMethodField()
    visibility = serializers.SerializerMethodField()
    artifacts = PortalDocumentArtifactSerializer(many=True)

    def get_source_kind(self, _obj: DocumentPublication) -> str:
        return "organization_document"

    def get_visibility(self, _obj: DocumentPublication) -> str:
        return "client_visible"

    def get_lifecycle_state(self, obj: DocumentPublication) -> str:
        if obj.retention_review_on is not None and obj.retention_review_on <= timezone.localdate():
            return "review_due"
        return "published"


class PortalDocumentDetailSerializer(PortalDocumentSerializer):
    sanitized_html = serializers.CharField(allow_blank=True)


class PortalDocumentResultSerializer(serializers.Serializer):
    results = PortalDocumentSerializer(many=True)
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    next_cursor = serializers.CharField(allow_null=True)


class DocumentPublicationResultSerializer(serializers.Serializer):
    results = DocumentPublicationSerializer(many=True)
    count = serializers.IntegerField()


class DocumentPlacementWriteSerializer(serializers.Serializer):
    operation = serializers.ChoiceField(
        choices=("reuse_document", "reuse_block", "create_block"), default="reuse_document"
    )
    source_document_id = serializers.UUIDField(required=False)
    source_block_id = serializers.UUIDField(required=False)
    resolution_mode = serializers.ChoiceField(choices=PlacementResolutionMode.choices, default="live")
    pinned_revision_id = serializers.UUIDField(required=False, allow_null=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    position = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    block_kind = serializers.ChoiceField(choices=BlockKind.choices, required=False, default=BlockKind.RICH_TEXT)
    block_name = serializers.CharField(
        max_length=240,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        validators=[_clean_name],
        default="",
    )
    markdown = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1_000_000,
        trim_whitespace=False,
        default="",
    )
    library_visible = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        operation = attrs["operation"]
        source_document_id = attrs.get("source_document_id")
        source_block_id = attrs.get("source_block_id")
        if operation == "reuse_document":
            if source_document_id is None:
                raise serializers.ValidationError({"source_document_id": "Choose a source document to reuse."})
            if source_block_id is not None:
                raise serializers.ValidationError({"source_block_id": "Choose either a document or a block."})
            if (
                "block_name" in self.initial_data
                or "block_kind" in self.initial_data
                or "markdown" in self.initial_data
                or "library_visible" in self.initial_data
            ):
                raise serializers.ValidationError("New-block fields cannot be supplied when reusing a document.")
            return attrs
        if operation == "reuse_block":
            if source_block_id is None:
                raise serializers.ValidationError({"source_block_id": "Choose a library block to reuse."})
            if source_document_id is not None:
                raise serializers.ValidationError({"source_document_id": "Choose either a document or a block."})
            if (
                "block_name" in self.initial_data
                or "block_kind" in self.initial_data
                or "markdown" in self.initial_data
            ):
                raise serializers.ValidationError("New-block fields cannot be supplied when reusing a library block.")
            return attrs
        if source_document_id is not None:
            raise serializers.ValidationError({"source_document_id": "New blocks cannot identify a source document."})
        if source_block_id is not None:
            raise serializers.ValidationError({"source_block_id": "New blocks cannot identify a source block."})
        if attrs["resolution_mode"] != PlacementResolutionMode.LIVE or attrs.get("pinned_revision_id") is not None:
            raise serializers.ValidationError("New blocks must begin as live local blocks.")
        return attrs


class DocumentPlacementUpdateSerializer(serializers.Serializer):
    resolution_mode = serializers.ChoiceField(choices=PlacementResolutionMode.choices)
    pinned_revision_id = serializers.UUIDField(required=False, allow_null=True)


class BlockLibraryQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True, default="")
    page_size = serializers.IntegerField(min_value=1, max_value=50, required=False, default=20)


class BlockLibraryItemSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    kind = serializers.ChoiceField(choices=BlockKind.choices)
    markdown = serializers.CharField(source="current_revision.markdown", allow_blank=True)
    revision_id = serializers.UUIDField(source="current_revision_id")
    revision_number = serializers.IntegerField(source="current_revision.revision_number")
    source_document_id = serializers.UUIDField(source="source_document.entity_id")
    source_document_title = serializers.CharField(source="source_document.entity.display_name")
    owner_kind = serializers.SerializerMethodField()
    owner_organization_id = serializers.UUIDField(source="organization.entity_id", allow_null=True)

    def get_owner_kind(self, obj: Block) -> str:
        return "organization" if obj.organization_id else "msp"


class BlockLibraryResultSerializer(serializers.Serializer):
    results = BlockLibraryItemSerializer(many=True)
    count = serializers.IntegerField()


class SharedBlockUpdateSerializer(serializers.Serializer):
    markdown = serializers.CharField(allow_blank=True, max_length=1_000_000, trim_whitespace=False)
    base_revision_id = serializers.UUIDField()


class ReuseAudienceSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    document_title = serializers.CharField()
    workspace_kind = serializers.ChoiceField(choices=("msp", "organization"))
    workspace_id = serializers.UUIDField(allow_null=True)
    workspace_name = serializers.CharField()
    relationship = serializers.ChoiceField(choices=("source", "placement", "listing"))
    resolution_mode = serializers.ChoiceField(choices=PlacementResolutionMode.choices)
    will_update = serializers.BooleanField()


class ReuseImpactSerializer(serializers.Serializer):
    block_id = serializers.UUIDField()
    block_name = serializers.CharField()
    revision_id = serializers.UUIDField()
    revision_number = serializers.IntegerField()
    checksum = serializers.CharField()
    markdown = serializers.CharField(allow_blank=True)
    can_edit_shared = serializers.BooleanField()
    can_detach = serializers.BooleanField()
    requires_mfa = serializers.BooleanField()
    audiences = ReuseAudienceSerializer(many=True)
    live_audience_count = serializers.IntegerField()
    pinned_audience_count = serializers.IntegerField()
    truncated = serializers.BooleanField()


class EntityMentionSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")
    entity_type = serializers.ChoiceField(
        choices=SEARCHABLE_ENTITY_TYPES,
        required=False,
        allow_blank=True,
        default="",
    )
    page = serializers.IntegerField(min_value=1, max_value=1000, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=20, required=False, default=15)


class EntityMentionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    entity_type = serializers.CharField()
    workspace_label = serializers.CharField()


class EntityMentionResultSerializer(serializers.Serializer):
    results = EntityMentionSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()


class DocumentPlacementSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    parent_id = serializers.SerializerMethodField()
    block_id = serializers.SerializerMethodField()
    block_name = serializers.SerializerMethodField()
    block_kind = serializers.SerializerMethodField()
    position = serializers.SerializerMethodField()
    depth = serializers.IntegerField()
    resolution_mode = serializers.SerializerMethodField()
    pinned_revision_id = serializers.SerializerMethodField()
    resolved_revision_id = serializers.SerializerMethodField()
    resolved_revision_number = serializers.SerializerMethodField()
    resolved_checksum = serializers.SerializerMethodField()
    resolved_markdown = serializers.CharField(source="revision.markdown", allow_blank=True)
    resolved_html = serializers.SerializerMethodField()
    is_primary = serializers.SerializerMethodField()

    def _placement(self, obj: ResolvedPlacement) -> DocumentPlacement:
        return obj.placement

    @extend_schema_field(serializers.UUIDField())
    def get_id(self, obj: ResolvedPlacement) -> UUID:
        return self._placement(obj).id

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_parent_id(self, obj: ResolvedPlacement) -> UUID | None:
        return self._placement(obj).parent_id

    @extend_schema_field(serializers.UUIDField())
    def get_block_id(self, obj: ResolvedPlacement) -> UUID:
        return self._placement(obj).block.entity_id

    @extend_schema_field(serializers.CharField())
    def get_block_name(self, obj: ResolvedPlacement) -> str:
        return self._placement(obj).block.entity.display_name

    @extend_schema_field(serializers.ChoiceField(choices=BlockKind.choices))
    def get_block_kind(self, obj: ResolvedPlacement) -> str:
        return self._placement(obj).block.kind

    @extend_schema_field(serializers.IntegerField())
    def get_position(self, obj: ResolvedPlacement) -> int:
        return self._placement(obj).position

    @extend_schema_field(serializers.ChoiceField(choices=PlacementResolutionMode.choices))
    def get_resolution_mode(self, obj: ResolvedPlacement) -> str:
        return self._placement(obj).resolution_mode

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_pinned_revision_id(self, obj: ResolvedPlacement) -> UUID | None:
        return self._placement(obj).pinned_revision_id

    @extend_schema_field(serializers.UUIDField())
    def get_resolved_revision_id(self, obj: ResolvedPlacement) -> UUID:
        return obj.revision.id

    @extend_schema_field(serializers.IntegerField())
    def get_resolved_revision_number(self, obj: ResolvedPlacement) -> int:
        return obj.revision.revision_number

    @extend_schema_field(serializers.CharField())
    def get_resolved_checksum(self, obj: ResolvedPlacement) -> str:
        return obj.revision.checksum

    def get_is_primary(self, obj: ResolvedPlacement) -> bool:
        placement = self._placement(obj)
        return placement.parent_id is None and placement.position == 0

    def get_resolved_html(self, obj: ResolvedPlacement) -> str:
        expanded: dict[UUID, str] = self.context.get("expanded_markdown", {})
        return render_markdown(
            expanded.get(obj.revision.id, obj.revision.markdown),
            entity_mentions=self.context.get("entity_mentions", {}),
            attachments=self.context.get("attachments", {}),
            key_resolutions=self.context.get("key_resolutions", {}),
        )


class DocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    title = serializers.CharField(source="entity.display_name")
    owner_kind = serializers.SerializerMethodField()
    owner_organization_id = serializers.UUIDField(source="organization.entity_id", allow_null=True)
    owner_organization_name = serializers.CharField(source="organization.entity.display_name", allow_null=True)
    is_reference = serializers.SerializerMethodField()
    category = serializers.ChoiceField(choices=DocumentCategory.choices)
    is_template = serializers.BooleanField()
    library_visible = serializers.BooleanField()
    template_enrollment_id = serializers.SerializerMethodField()
    template_applied_revision_id = serializers.SerializerMethodField()
    template_source_id = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    attachment_count = serializers.SerializerMethodField()
    primary_file = serializers.SerializerMethodField()
    primary_file_versions = serializers.SerializerMethodField()
    publications = serializers.SerializerMethodField()
    publication_count = serializers.SerializerMethodField()
    markdown = serializers.SerializerMethodField()
    block_id = serializers.SerializerMethodField()
    current_revision_id = serializers.SerializerMethodField()
    revision_number = serializers.SerializerMethodField()
    checksum = serializers.SerializerMethodField()
    resolved_markdown = serializers.SerializerMethodField()
    placements = serializers.SerializerMethodField()
    placement_count = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_owner_kind(self, obj: Document) -> str:
        return "organization" if obj.organization_id else "msp"

    def get_is_reference(self, obj: Document) -> bool:
        workspace_organization_id = self.context.get("workspace_organization_id")
        return workspace_organization_id is not None and obj.organization_id is None

    def _template_enrollment(self, obj: Document):  # type: ignore[no-untyped-def]
        try:
            return obj.template_enrollment
        except ObjectDoesNotExist:
            return None

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_template_enrollment_id(self, obj: Document):  # type: ignore[no-untyped-def]
        enrollment = self._template_enrollment(obj)
        return enrollment.id if enrollment is not None and enrollment.archived_at is None else None

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_template_applied_revision_id(self, obj: Document):  # type: ignore[no-untyped-def]
        enrollment = self._template_enrollment(obj)
        return enrollment.applied_revision_id if enrollment is not None and enrollment.archived_at is None else None

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_template_source_id(self, obj: Document):  # type: ignore[no-untyped-def]
        enrollment = self._template_enrollment(obj)
        if enrollment is None or enrollment.archived_at is not None:
            return None
        return enrollment.source_template.entity_id

    @extend_schema_field(DocumentAttachmentSerializer(many=True))
    def get_attachments(self, obj: Document) -> list[dict[str, object]]:
        records = getattr(obj, "active_attachments", None)
        if records is None:
            records = obj.attachments.filter(
                archived_at__isnull=True,
                purpose=DocumentAttachmentPurpose.ATTACHMENT,
            ).order_by("original_filename", "entity_id")
        else:
            records = [item for item in records if item.purpose == DocumentAttachmentPurpose.ATTACHMENT]
        return cast(list[dict[str, object]], DocumentAttachmentSerializer(records, many=True).data)

    def get_attachment_count(self, obj: Document) -> int:
        records = getattr(obj, "active_attachments", None)
        if records is not None:
            return sum(item.purpose == DocumentAttachmentPurpose.ATTACHMENT for item in records)
        return obj.attachments.filter(
            archived_at__isnull=True,
            purpose=DocumentAttachmentPurpose.ATTACHMENT,
        ).count()

    def _primary_file_versions(self, obj: Document) -> list[DocumentAttachment]:
        cached = obj.__dict__.get("_tekdocs_primary_file_versions")
        if cached is not None:
            return cast(list[DocumentAttachment], cached)
        records = getattr(obj, "active_attachments", None)
        if records is None:
            versions = list(
                obj.attachments.filter(
                    archived_at__isnull=True,
                    purpose=DocumentAttachmentPurpose.PRIMARY_FILE,
                )
                .select_related("entity", "replaces__entity")
                .order_by("-version_number", "-created_at")
            )
        else:
            versions = sorted(
                (item for item in records if item.purpose == DocumentAttachmentPurpose.PRIMARY_FILE),
                key=lambda item: (item.version_number or 0, item.created_at),
                reverse=True,
            )
        obj.__dict__["_tekdocs_primary_file_versions"] = versions
        return versions

    def _serialize_primary_file(self, record: DocumentAttachment, *, is_current: bool) -> dict[str, object]:
        data = cast(dict[str, object], DocumentAttachmentSerializer(record).data)
        replaced = record.replaces if record.replaces_id else None
        data.update(
            {
                "version_number": record.version_number,
                "replaces_id": replaced.entity_id if replaced is not None else None,
                "is_current": is_current,
            }
        )
        return data

    @extend_schema_field(DocumentPrimaryFileSerializer(allow_null=True))
    def get_primary_file(self, obj: Document) -> dict[str, object] | None:
        versions = self._primary_file_versions(obj)
        return self._serialize_primary_file(versions[0], is_current=True) if versions else None

    @extend_schema_field(DocumentPrimaryFileSerializer(many=True))
    def get_primary_file_versions(self, obj: Document) -> list[dict[str, object]]:
        return [
            self._serialize_primary_file(record, is_current=index == 0)
            for index, record in enumerate(self._primary_file_versions(obj))
        ]

    @extend_schema_field(DocumentPublicationSerializer(many=True))
    def get_publications(self, obj: Document) -> list[dict[str, object]]:
        records = getattr(obj, "retained_publications", None)
        if records is None:
            records = obj.publications.select_related("entity", "published_by").order_by("-published_at", "id")
        return cast(list[dict[str, object]], DocumentPublicationSerializer(records, many=True).data)

    def get_publication_count(self, obj: Document) -> int:
        records = getattr(obj, "retained_publications", None)
        return len(records) if records is not None else obj.publications.count()

    def _placement(self, obj: Document) -> DocumentPlacement | None:
        placements = cast(tuple[DocumentPlacement, ...], getattr(obj, "active_placements", ()))
        return next(
            (placement for placement in placements if placement.parent_id is None and placement.position == 0),
            None,
        )

    def _resolved(self, obj: Document) -> ResolvedDocument:
        resolved = cast(ResolvedDocument | None, getattr(obj, "_tekdocs_resolved_document", None))
        if resolved is None:
            resolved = resolve_document(obj)
            obj.__dict__["_tekdocs_resolved_document"] = resolved
        return resolved

    def get_markdown(self, obj: Document) -> str:
        placement = self._placement(obj)
        revision = placement.block.current_revision if placement is not None else None
        return revision.markdown if revision is not None else ""

    def get_block_id(self, obj: Document) -> UUID | None:
        placement = self._placement(obj)
        return placement.block.entity_id if placement is not None else None

    def get_current_revision_id(self, obj: Document) -> UUID | None:
        placement = self._placement(obj)
        return placement.block.current_revision_id if placement is not None else None

    def get_revision_number(self, obj: Document) -> int | None:
        placement = self._placement(obj)
        revision = placement.block.current_revision if placement is not None else None
        return revision.revision_number if revision is not None else None

    def get_checksum(self, obj: Document) -> str:
        placement = self._placement(obj)
        revision = placement.block.current_revision if placement is not None else None
        return revision.checksum if revision is not None else ""

    def get_resolved_markdown(self, obj: Document) -> str:
        return self._resolved(obj).markdown

    @extend_schema_field(DocumentPlacementSerializer(many=True))
    def get_placements(self, obj: Document) -> list[dict[str, object]]:
        context: dict[str, object] = {}
        workspace = self.context.get("workspace")
        if workspace is not None:
            markdown = self._resolved(obj).markdown
            expanded_markdown = expand_rendered_content_keys(
                workspace=workspace, document=obj, markdown=markdown
            )
            expanded_placements = {
                placement.revision.id: expand_rendered_content_keys(
                    workspace=workspace,
                    document=obj,
                    markdown=placement.revision.markdown,
                )
                for placement in self._resolved(obj).placements
            }
            context = {
                "entity_mentions": resolve_entity_mentions(workspace=workspace, markdown=expanded_markdown),
                "attachments": resolve_rendered_attachments(
                    workspace=workspace, document=obj, markdown=expanded_markdown
                ),
                "key_resolutions": resolve_rendered_keys(
                    workspace=workspace, document=obj, markdown=expanded_markdown
                ),
                "expanded_markdown": expanded_placements,
            }
        return cast(
            list[dict[str, object]],
            DocumentPlacementSerializer(self._resolved(obj).placements, many=True, context=context).data,
        )

    def get_placement_count(self, obj: Document) -> int:
        return len(self._resolved(obj).placements)


class DocumentRestructureResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("restructured", "already_restructured"))
    section_count = serializers.IntegerField()
    document = DocumentSerializer()


class BlockRevisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    parent_id = serializers.UUIDField(allow_null=True)
    revision_number = serializers.IntegerField()
    checksum = serializers.CharField()
    created_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    is_current = serializers.SerializerMethodField()

    def get_created_by(self, obj: BlockRevision) -> str | None:
        return obj.created_by.get_full_name() or obj.created_by.get_username() if obj.created_by else None

    def get_is_current(self, obj: BlockRevision) -> bool:
        return bool(obj.id == self.context.get("current_revision_id"))


class BlockRevisionDetailSerializer(BlockRevisionSerializer):
    markdown = serializers.CharField()
    diff_from_parent = serializers.SerializerMethodField()

    def get_diff_from_parent(self, obj: BlockRevision) -> str:
        value = self.context.get("diff_from_parent", "")
        return value if isinstance(value, str) else ""


class BlockRevisionResultSerializer(serializers.Serializer):
    results = BlockRevisionSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()


class BlockRevisionListQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=50)


class RevisionConflictSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()
    submitted_base_revision_id = serializers.UUIDField()
    current_revision = BlockRevisionDetailSerializer()
    diff = serializers.CharField()


class DocumentResultSerializer(serializers.Serializer):
    results = DocumentSerializer(many=True)
    count = serializers.IntegerField()


class DocumentationReferenceWriteSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()


class DocumentationReferenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    organization_id = serializers.UUIDField(source="organization.entity_id")
    organization_name = serializers.CharField(source="organization.entity.display_name")
    created_at = serializers.DateTimeField()
