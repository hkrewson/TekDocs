from typing import cast
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .collection_pagination import StrictQuerySerializer
from .content_index_models import ContentNode
from .content_read import RepositoryContentNotIndexed
from .document_attachments import resolve_rendered_attachments
from .document_authoring_serializers import (
    DocumentCreateSerializer as DocumentCreateSerializer,
)
from .document_authoring_serializers import (
    DocumentListQuerySerializer as DocumentListQuerySerializer,
)
from .document_authoring_serializers import (
    DocumentPreflightFindingSerializer as DocumentPreflightFindingSerializer,
)
from .document_authoring_serializers import (
    DocumentPreflightQuerySerializer as DocumentPreflightQuerySerializer,
)
from .document_authoring_serializers import (
    DocumentPreflightSerializer as DocumentPreflightSerializer,
)
from .document_authoring_serializers import (
    DocumentRestructureApplySerializer as DocumentRestructureApplySerializer,
)
from .document_authoring_serializers import (
    DocumentRestructureDependenciesSerializer as DocumentRestructureDependenciesSerializer,
)
from .document_authoring_serializers import (
    DocumentRestructureNoticeSerializer as DocumentRestructureNoticeSerializer,
)
from .document_authoring_serializers import (
    DocumentRestructurePreviewSerializer as DocumentRestructurePreviewSerializer,
)
from .document_authoring_serializers import (
    DocumentRestructureSectionSerializer as DocumentRestructureSectionSerializer,
)
from .document_authoring_serializers import (
    DocumentTopicConversionPreviewSerializer as DocumentTopicConversionPreviewSerializer,
)
from .document_authoring_serializers import (
    DocumentTopicConversionSerializer as DocumentTopicConversionSerializer,
)
from .document_authoring_serializers import (
    DocumentUpdateSerializer as DocumentUpdateSerializer,
)
from .document_authoring_serializers import (
    FileBackedDocumentCreateSerializer as FileBackedDocumentCreateSerializer,
)
from .document_authoring_serializers import (
    MarkdownImportSerializer as MarkdownImportSerializer,
)
from .document_authoring_serializers import (
    PreflightCodeSerializer as PreflightCodeSerializer,
)
from .document_authoring_serializers import (
    TopicSchemaCatalogSerializer as TopicSchemaCatalogSerializer,
)
from .document_authoring_serializers import (
    TopicSchemaSerializer as TopicSchemaSerializer,
)
from .document_authoring_serializers import TopicSectionSerializer as TopicSectionSerializer
from .document_file_serializers import DocumentAttachmentSerializer as DocumentAttachmentSerializer
from .document_file_serializers import DocumentAttachmentWriteSerializer as DocumentAttachmentWriteSerializer
from .document_file_serializers import DocumentFileQuerySerializer as DocumentFileQuerySerializer
from .document_file_serializers import DocumentFileResultSerializer as DocumentFileResultSerializer
from .document_file_serializers import DocumentPrimaryFileSerializer as DocumentPrimaryFileSerializer
from .document_key_freeze import expand_rendered_content_keys
from .document_key_resolution import resolve_rendered_keys
from .document_publication_serializers import (
    DocumentPublicationControlWriteSerializer as DocumentPublicationControlWriteSerializer,
)
from .document_publication_serializers import (
    DocumentPublicationDetailSerializer as DocumentPublicationDetailSerializer,
)
from .document_publication_serializers import (
    DocumentPublicationResultSerializer as DocumentPublicationResultSerializer,
)
from .document_publication_serializers import DocumentPublicationSerializer as DocumentPublicationSerializer
from .document_publication_serializers import DocumentPublicationWriteSerializer as DocumentPublicationWriteSerializer
from .document_publication_serializers import PortalDocumentDetailSerializer as PortalDocumentDetailSerializer
from .document_publication_serializers import PortalDocumentResultSerializer as PortalDocumentResultSerializer
from .document_publication_serializers import PortalDocumentSerializer as PortalDocumentSerializer
from .document_reuse_serializers import BlockLibraryItemSerializer as BlockLibraryItemSerializer
from .document_reuse_serializers import BlockLibraryQuerySerializer as BlockLibraryQuerySerializer
from .document_reuse_serializers import BlockLibraryResultSerializer as BlockLibraryResultSerializer
from .document_reuse_serializers import DocumentPlacementSerializer as DocumentPlacementSerializer
from .document_reuse_serializers import DocumentPlacementUpdateSerializer as DocumentPlacementUpdateSerializer
from .document_reuse_serializers import DocumentPlacementWriteSerializer as DocumentPlacementWriteSerializer
from .document_reuse_serializers import ReuseAudienceSerializer as ReuseAudienceSerializer
from .document_reuse_serializers import ReuseImpactSerializer as ReuseImpactSerializer
from .document_reuse_serializers import SharedBlockUpdateSerializer as SharedBlockUpdateSerializer
from .document_review_serializers import (
    DocumentReviewDecisionWriteSerializer as DocumentReviewDecisionWriteSerializer,
)
from .document_review_serializers import (
    DocumentReviewRequestWriteSerializer as DocumentReviewRequestWriteSerializer,
)
from .document_template_serializers import (
    DocumentTemplateInstantiateSerializer as DocumentTemplateInstantiateSerializer,
)
from .document_template_serializers import (
    DocumentTemplateRolloutApplySerializer as DocumentTemplateRolloutApplySerializer,
)
from .document_template_serializers import (
    DocumentTemplateRolloutPreviewSerializer as DocumentTemplateRolloutPreviewSerializer,
)
from .document_template_serializers import (
    DocumentTemplateRolloutResultSerializer as DocumentTemplateRolloutResultSerializer,
)
from .documents import ResolvedDocument, resolve_document
from .entity_mentions import resolve_entity_mentions
from .models import (
    BlockRevision,
    Document,
    DocumentAttachment,
    DocumentAttachmentPurpose,
    DocumentAuthority,
    DocumentAuthorityMode,
    DocumentCategory,
    DocumentPlacement,
    DocumentReviewState,
    DocumentTopicType,
    LocationKind,
    Organization,
    OrganizationAccessMode,
    OrganizationKind,
    OrganizationTaxonomyTerm,
    PersonAssociationKind,
    Site,
    Taxonomy,
    TaxonomyTerm,
    TaxonomyTermStatus,
    WorkspaceRepository,
)
from .relationships import SEARCHABLE_ENTITY_TYPES
from .taxonomies import document_tag_labels, document_term_records


def _clean_name(value: str) -> str:
    if any(ord(character) < 32 for character in value):
        raise serializers.ValidationError("Name cannot contain control characters.")
    return value


class OrganizationWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    legal_name = serializers.CharField(max_length=240, trim_whitespace=True, required=False, allow_blank=True)
    website = serializers.URLField(max_length=500, required=False, allow_blank=True)
    billing_contact_name = serializers.CharField(max_length=240, trim_whitespace=True, required=False, allow_blank=True)
    billing_email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    billing_phone = serializers.CharField(max_length=64, trim_whitespace=True, required=False, allow_blank=True)
    billing_address_line_1 = serializers.CharField(
        max_length=240, trim_whitespace=True, required=False, allow_blank=True
    )
    billing_address_line_2 = serializers.CharField(
        max_length=240, trim_whitespace=True, required=False, allow_blank=True
    )
    billing_city = serializers.CharField(max_length=120, trim_whitespace=True, required=False, allow_blank=True)
    billing_region = serializers.CharField(max_length=120, trim_whitespace=True, required=False, allow_blank=True)
    billing_postal_code = serializers.CharField(max_length=32, trim_whitespace=True, required=False, allow_blank=True)
    billing_country_code = serializers.CharField(max_length=2, trim_whitespace=True, required=False, allow_blank=True)
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

    def validate_billing_country_code(self, value: str) -> str:
        from .countries import COUNTRY_CODES

        normalized = value.upper()
        if normalized and normalized not in COUNTRY_CODES:
            raise serializers.ValidationError("Choose a supported ISO country.")
        return normalized


class OrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    legal_name = serializers.CharField()
    website = serializers.URLField()
    billing_contact_name = serializers.CharField()
    billing_email = serializers.EmailField()
    billing_phone = serializers.CharField()
    billing_address_line_1 = serializers.CharField()
    billing_address_line_2 = serializers.CharField()
    billing_city = serializers.CharField()
    billing_region = serializers.CharField()
    billing_postal_code = serializers.CharField()
    billing_country_code = serializers.CharField()
    access_mode = serializers.ChoiceField(choices=OrganizationAccessMode.choices)
    classifications = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_classifications(self, organization: Organization) -> list[str]:
        return sorted(classification.kind for classification in organization.classifications.all())


class OrganizationQuerySerializer(StrictQuerySerializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")
    classification = serializers.ChoiceField(
        choices=OrganizationKind.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    ordering = serializers.ChoiceField(
        choices=("name", "-name", "legal_name", "-legal_name", "website", "-website"),
        required=False,
        default="name",
    )
    page = serializers.IntegerField(min_value=1, max_value=100_000, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=25)


class OrganizationResultSerializer(serializers.Serializer):
    results = OrganizationSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()


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


class SiteQuerySerializer(StrictQuerySerializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")
    ordering = serializers.ChoiceField(
        choices=(
            "name",
            "-name",
            "code",
            "-code",
            "city",
            "-city",
            "region",
            "-region",
            "country_code",
            "-country_code",
            "timezone",
            "-timezone",
        ),
        required=False,
        default="name",
    )
    page = serializers.IntegerField(min_value=1, max_value=1000, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=25)


class SiteResultSerializer(serializers.Serializer):
    results = SiteSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()


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


class TemplateLibraryQuerySerializer(StrictQuerySerializer):
    q = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=25)


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


class DocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    title = serializers.CharField(source="entity.display_name")
    owner_kind = serializers.SerializerMethodField()
    owner_organization_id = serializers.UUIDField(source="organization.entity_id", allow_null=True)
    owner_organization_name = serializers.CharField(source="organization.entity.display_name", allow_null=True)
    is_reference = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    topic_type = serializers.SerializerMethodField()
    topic_schema_version = serializers.SerializerMethodField()
    is_template = serializers.BooleanField()
    library_visible = serializers.BooleanField()
    collection = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    taxonomy_terms = serializers.SerializerMethodField()
    owner_id = serializers.UUIDField(allow_null=True)
    owner_name = serializers.CharField(source="owner.display_name", allow_null=True)
    review_due_on = serializers.DateField(allow_null=True)
    review_state = serializers.ChoiceField(choices=DocumentReviewState.choices)
    health_status = serializers.CharField()
    review_requested_by_id = serializers.UUIDField(allow_null=True)
    review_requested_by_name = serializers.CharField(source="review_requested_by.display_name", allow_null=True)
    review_requested_at = serializers.DateTimeField(allow_null=True)
    reviewer_id = serializers.UUIDField(allow_null=True)
    reviewer_name = serializers.CharField(source="reviewer.display_name", allow_null=True)
    review_decided_at = serializers.DateTimeField(allow_null=True)
    last_reviewed_by_id = serializers.UUIDField(allow_null=True)
    last_reviewed_by_name = serializers.CharField(source="last_reviewed_by.display_name", allow_null=True)
    last_reviewed_at = serializers.DateTimeField(allow_null=True)
    review_note = serializers.CharField(allow_blank=True)
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
    content_authority = serializers.SerializerMethodField()
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

    def _authority_by_content_id(self, obj: Document) -> dict[UUID, str]:
        authority_by_content_id = self.context.get("_document_authority_by_content_id")
        if authority_by_content_id is None:
            parent = self.parent
            root_instance = self.root.instance
            if isinstance(parent, serializers.ListSerializer) and isinstance(root_instance, dict):
                records = root_instance.get("results", ())
                content_ids = [record.id for record in records]
            elif isinstance(parent, serializers.ListSerializer) and parent.instance is not None:
                content_ids = [record.id for record in parent.instance]
            else:
                content_ids = [obj.id]
            authority_by_content_id = dict(
                DocumentAuthority.objects.filter(content_id__in=content_ids).values_list(
                    "content_id", "authority"
                )
            )
            self.context["_document_authority_by_content_id"] = authority_by_content_id
        return cast(dict[UUID, str], authority_by_content_id)

    def _is_repository_owned(self, obj: Document) -> bool:
        return self._authority_by_content_id(obj).get(obj.id) == DocumentAuthorityMode.REPOSITORY

    def _repository_node(self, obj: Document) -> ContentNode | None:
        if not self._is_repository_owned(obj):
            return None
        cached = cast(dict[UUID, ContentNode], self.context.setdefault("_document_repository_nodes", {}))
        if obj.id in cached:
            return cached[obj.id]
        repository = WorkspaceRepository.objects.filter(workspace_id=obj.entity.workspace_id).first()
        if (
            repository is None
            or repository.accepted_commit_id is None
            or repository.accepted_commit_id != repository.indexed_commit_id
        ):
            raise RepositoryContentNotIndexed()
        node = ContentNode.objects.filter(
            repository=repository,
            content_id=obj.id,
            indexed_commit_id=repository.accepted_commit_id,
        ).first()
        if node is None:
            raise RepositoryContentNotIndexed()
        cached[obj.id] = node
        return node

    def _repository_properties(self, obj: Document) -> dict[str, object] | None:
        node = self._repository_node(obj)
        if node is None:
            return None
        properties = node.frontmatter.get("properties", {})
        return properties if isinstance(properties, dict) else {}

    @extend_schema_field(serializers.ChoiceField(choices=DocumentCategory.choices))
    def get_category(self, obj: Document) -> str:
        properties = self._repository_properties(obj)
        return str(properties.get("category", "general")) if properties is not None else obj.category

    @extend_schema_field(serializers.ChoiceField(choices=DocumentTopicType.choices))
    def get_topic_type(self, obj: Document) -> str:
        node = self._repository_node(obj)
        return node.topic_type if node is not None else obj.topic_type

    @extend_schema_field(serializers.IntegerField())
    def get_topic_schema_version(self, obj: Document) -> int:
        node = self._repository_node(obj)
        return node.topic_schema_version or 1 if node is not None else obj.topic_schema_version

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_collection(self, obj: Document) -> str:
        properties = self._repository_properties(obj)
        return str(properties.get("collection", obj.collection)) if properties is not None else obj.collection

    @extend_schema_field(serializers.ChoiceField(choices=DocumentAuthorityMode.choices))
    def get_content_authority(self, obj: Document) -> str:
        # Legacy PostgreSQL authority is the default for documents without an explicit handoff row.
        return str(self._authority_by_content_id(obj).get(obj.id) or DocumentAuthorityMode.LEGACY)

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_tags(self, obj: Document) -> list[str]:
        properties = self._repository_properties(obj)
        if properties is not None:
            tags = properties.get("tags", [])
            return [str(item) for item in tags] if isinstance(tags, list) else []
        return document_tag_labels(obj)

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_taxonomy_terms(self, obj: Document) -> list[dict[str, object]]:
        node = self._repository_node(obj)
        if node is not None:
            return self._repository_taxonomy_terms(obj, node)
        result = []
        for assignment in document_term_records(obj):
            selected = assignment.term or assignment.local_term
            if selected is None:
                continue
            if assignment.term is not None:
                version = assignment.term.version
            elif assignment.local_term is not None:
                version = assignment.local_term.taxonomy_version
            else:
                continue
            result.append(
                {
                    "id": selected.id,
                    "taxonomy_id": assignment.taxonomy_id,
                    "taxonomy_key": assignment.taxonomy.key,
                    "taxonomy_version": version.version,
                    "stable_key": selected.stable_key,
                    "label": selected.label,
                    "description": selected.description,
                    "local": assignment.local_term_id is not None,
                }
            )
        return result

    def _repository_taxonomy_terms(self, obj: Document, node: ContentNode) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        taxonomy_keys = node.taxonomy_keys
        if not isinstance(taxonomy_keys, dict):
            return result
        taxonomies = {
            taxonomy.key: taxonomy
            for taxonomy in Taxonomy.objects.filter(
                tenant_id=obj.tenant_id,
                key__in=taxonomy_keys,
                archived_at__isnull=True,
            ).select_related("current_version")
        }
        for key, stable_keys in taxonomy_keys.items():
            taxonomy = taxonomies.get(key)
            if taxonomy is None or taxonomy.current_version_id is None or not isinstance(stable_keys, list):
                continue
            for stable_key in stable_keys:
                term = TaxonomyTerm.objects.filter(
                    taxonomy=taxonomy,
                    version_id=taxonomy.current_version_id,
                    stable_key=stable_key,
                    status=TaxonomyTermStatus.ACTIVE,
                ).first()
                local_term = None
                if term is None and obj.organization_id is not None:
                    local_term = OrganizationTaxonomyTerm.objects.filter(
                        organization_id=obj.organization_id,
                        taxonomy=taxonomy,
                        taxonomy_version_id=taxonomy.current_version_id,
                        stable_key=stable_key,
                        archived_at__isnull=True,
                    ).first()
                selected = term or local_term
                if selected is None:
                    continue
                if taxonomy.current_version is None:
                    continue
                result.append(
                    {
                        "id": selected.id,
                        "taxonomy_id": taxonomy.id,
                        "taxonomy_key": taxonomy.key,
                        "taxonomy_version": taxonomy.current_version.version,
                        "stable_key": selected.stable_key,
                        "label": selected.label,
                        "description": selected.description,
                        "local": local_term is not None,
                    }
                )
        return result

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
        if self._is_repository_owned(obj):
            return ""
        placement = self._placement(obj)
        revision = placement.block.current_revision if placement is not None else None
        return revision.markdown if revision is not None else ""

    def get_block_id(self, obj: Document) -> UUID | None:
        if self._is_repository_owned(obj):
            return None
        placement = self._placement(obj)
        return placement.block.entity_id if placement is not None else None

    def get_current_revision_id(self, obj: Document) -> UUID | None:
        if self._is_repository_owned(obj):
            return None
        placement = self._placement(obj)
        return placement.block.current_revision_id if placement is not None else None

    def get_revision_number(self, obj: Document) -> int | None:
        if self._is_repository_owned(obj):
            return None
        placement = self._placement(obj)
        revision = placement.block.current_revision if placement is not None else None
        return revision.revision_number if revision is not None else None

    def get_checksum(self, obj: Document) -> str:
        if self._is_repository_owned(obj):
            return ""
        placement = self._placement(obj)
        revision = placement.block.current_revision if placement is not None else None
        return revision.checksum if revision is not None else ""

    def get_resolved_markdown(self, obj: Document) -> str:
        if self._is_repository_owned(obj):
            return ""
        return self._resolved(obj).markdown

    @extend_schema_field(DocumentPlacementSerializer(many=True))
    def get_placements(self, obj: Document) -> list[dict[str, object]]:
        if self._is_repository_owned(obj):
            return []
        context: dict[str, object] = {}
        workspace = self.context.get("workspace")
        if workspace is not None:
            markdown = self._resolved(obj).markdown
            expanded_markdown = expand_rendered_content_keys(workspace=workspace, document=obj, markdown=markdown)
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
                "key_resolutions": resolve_rendered_keys(workspace=workspace, document=obj, markdown=expanded_markdown),
                "expanded_markdown": expanded_placements,
            }
        return cast(
            list[dict[str, object]],
            DocumentPlacementSerializer(self._resolved(obj).placements, many=True, context=context).data,
        )

    def get_placement_count(self, obj: Document) -> int:
        if self._is_repository_owned(obj):
            return 0
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
    topic_type = serializers.ChoiceField(choices=DocumentTopicType.choices)
    topic_schema_version = serializers.IntegerField()
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


class TemplateLibraryResultSerializer(DocumentResultSerializer):
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()


class DocumentOperationsWriteSerializer(serializers.Serializer):
    owner_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    review_due_on = serializers.DateField(required=False, allow_null=True, default=None)
    collection = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    tags = serializers.ListField(
        child=serializers.CharField(max_length=40, trim_whitespace=True),
        max_length=20,
        required=False,
        default=list,
    )
    taxonomy_term_ids = serializers.ListField(
        child=serializers.UUIDField(), max_length=20, required=False, allow_empty=True
    )


class DocumentOperationsChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    can_approve = serializers.BooleanField()


class DocumentSearchHitSerializer(DocumentSerializer):
    matching_excerpt = serializers.SerializerMethodField()

    def get_matching_excerpt(self, obj: Document) -> str:
        return str(getattr(obj, "matching_excerpt", ""))


class DocumentFacetSerializer(serializers.Serializer):
    value = serializers.CharField()
    count = serializers.IntegerField()


class DocumentSearchResultSerializer(serializers.Serializer):
    results = DocumentSearchHitSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()
    collections = DocumentFacetSerializer(many=True)
    tags = DocumentFacetSerializer(many=True)
    health = DocumentFacetSerializer(many=True)


class DocumentationReferenceWriteSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()


class DocumentationReferenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    organization_id = serializers.UUIDField(source="organization.entity_id")
    organization_name = serializers.CharField(source="organization.entity.display_name")
    created_at = serializers.DateTimeField()
