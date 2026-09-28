"""API serializers for document composition and reusable block workflows."""

from uuid import UUID

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .collection_pagination import StrictQuerySerializer
from .documents import ResolvedPlacement
from .models import Block, BlockKind, DocumentPlacement, PlacementAudienceProfile, PlacementResolutionMode
from .rendering import render_markdown


def _clean_name(value: str) -> str:
    if any(ord(character) < 32 for character in value):
        raise serializers.ValidationError("Name cannot contain control characters.")
    return value


class DocumentPlacementWriteSerializer(serializers.Serializer):
    operation = serializers.ChoiceField(
        choices=("reuse_document", "reuse_block", "create_block"), default="reuse_document"
    )
    source_document_id = serializers.UUIDField(required=False)
    source_block_id = serializers.UUIDField(required=False)
    resolution_mode = serializers.ChoiceField(choices=PlacementResolutionMode.choices, default="live")
    audience_profile = serializers.ChoiceField(
        choices=PlacementAudienceProfile.choices,
        default=PlacementAudienceProfile.SHARED,
    )
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
    resolution_mode = serializers.ChoiceField(choices=PlacementResolutionMode.choices, required=False)
    pinned_revision_id = serializers.UUIDField(required=False, allow_null=True)
    audience_profile = serializers.ChoiceField(choices=PlacementAudienceProfile.choices, required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if not attrs:
            raise serializers.ValidationError("Provide a resolution mode or audience profile to update.")
        return attrs


class BlockLibraryQuerySerializer(StrictQuerySerializer):
    q = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True, default="")
    page_size = serializers.IntegerField(min_value=1, max_value=50, required=False, default=20)
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    exclude_document = serializers.UUIDField(required=False)


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
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()


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


class DocumentPlacementSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    parent_id = serializers.SerializerMethodField()
    block_id = serializers.SerializerMethodField()
    block_name = serializers.SerializerMethodField()
    block_kind = serializers.SerializerMethodField()
    position = serializers.SerializerMethodField()
    depth = serializers.IntegerField()
    resolution_mode = serializers.SerializerMethodField()
    audience_profile = serializers.SerializerMethodField()
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

    @extend_schema_field(serializers.ChoiceField(choices=PlacementAudienceProfile.choices))
    def get_audience_profile(self, obj: ResolvedPlacement) -> str:
        return self._placement(obj).audience_profile

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
