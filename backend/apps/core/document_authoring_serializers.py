"""API serializers for document authoring, import, preflight, and restructuring."""

from rest_framework import serializers

from .collection_pagination import StrictQuerySerializer
from .models import (
    BlockKind,
    DocumentCategory,
    DocumentReviewState,
    DocumentTopicType,
    PublicationAudience,
)


def _clean_name(value: str) -> str:
    if any(ord(character) < 32 for character in value):
        raise serializers.ValidationError("Name cannot contain control characters.")
    return value


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
    topic_type = serializers.ChoiceField(
        choices=DocumentTopicType.choices, required=False, default=DocumentTopicType.UNSTRUCTURED
    )


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


class DocumentTopicConversionSerializer(serializers.Serializer):
    topic_type = serializers.ChoiceField(choices=DocumentTopicType.choices)
    base_revision_id = serializers.UUIDField()
    apply = serializers.BooleanField(required=False, default=False)


class DocumentPreflightQuerySerializer(serializers.Serializer):
    audience = serializers.ChoiceField(
        choices=PublicationAudience.choices, required=False, default=PublicationAudience.MSP_INTERNAL
    )


class DocumentPreflightFindingSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=("blocker", "warning", "info"))
    summary = serializers.CharField()
    remediation = serializers.CharField()
    target = serializers.CharField()
    section_id = serializers.CharField(allow_null=True)
    line = serializers.IntegerField(allow_null=True)


class DocumentPreflightSerializer(serializers.Serializer):
    version = serializers.CharField()
    scope = serializers.CharField()
    scope_id = serializers.UUIDField()
    composition_digest = serializers.CharField()
    audience = serializers.ChoiceField(choices=PublicationAudience.choices)
    valid = serializers.BooleanField()
    counts = serializers.DictField(child=serializers.IntegerField())
    findings = DocumentPreflightFindingSerializer(many=True)


class TopicSectionSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()


class TopicSchemaSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=DocumentTopicType.choices)
    label = serializers.CharField()
    description = serializers.CharField()
    schema_version = serializers.IntegerField()
    starter_markdown = serializers.CharField(allow_blank=True)
    sections = TopicSectionSerializer(many=True)


class PreflightCodeSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=("blocker", "warning", "info"))
    summary = serializers.CharField()
    remediation = serializers.CharField()


class TopicSchemaCatalogSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    topics = TopicSchemaSerializer(many=True)
    preflight_codes = PreflightCodeSerializer(many=True)


class DocumentTopicConversionPreviewSerializer(serializers.Serializer):
    topic_type = serializers.ChoiceField(choices=DocumentTopicType.choices)
    topic_schema_version = serializers.IntegerField()
    base_revision_id = serializers.UUIDField()
    original_markdown = serializers.CharField(allow_blank=True)
    converted_markdown = serializers.CharField(allow_blank=True)
    findings = serializers.ListField(child=serializers.DictField())


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


class DocumentListQuerySerializer(StrictQuerySerializer):
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
    collection = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    tag = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    health = serializers.ChoiceField(
        choices=("", "attention", "current", "stale", "unreviewed", "unowned", "pending", "changes_requested"),
        required=False,
        allow_blank=True,
        default="",
    )
    exclude_document = serializers.UUIDField(required=False)
    review_state = serializers.ChoiceField(
        choices=(("", "All"), *DocumentReviewState.choices),
        required=False,
        allow_blank=True,
        default="",
    )
    owner_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    ordering = serializers.ChoiceField(
        choices=("title", "-title", "updated_at", "-updated_at", "category", "-category"),
        required=False,
        default="title",
    )
    page = serializers.IntegerField(min_value=1, max_value=100_000, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=25)


class MarkdownImportSerializer(serializers.Serializer):
    file = serializers.FileField()
    title = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    category = serializers.ChoiceField(choices=DocumentCategory.choices, default=DocumentCategory.GENERAL)
    is_template = serializers.BooleanField(default=False)
