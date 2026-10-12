"""API serializers for managed document files and attachment versions."""

from django.urls import reverse
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .collection_pagination import StrictQuerySerializer
from .models import DocumentAttachmentPurpose


class DocumentAttachmentWriteSerializer(serializers.Serializer):
    file = serializers.FileField()


class RepositoryPrimaryFileWriteSerializer(DocumentAttachmentWriteSerializer):
    expected_current_id = serializers.UUIDField(required=False, allow_null=True, default=None)


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


class DocumentFileQuerySerializer(StrictQuerySerializer):
    q = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True, default="")
    kind = serializers.ChoiceField(
        choices=("", "primary", "attachment"), required=False, allow_blank=True, default=""
    )
    ordering = serializers.ChoiceField(
        choices=(
            "filename", "-filename", "document", "-document", "kind", "-kind",
            "type", "-type", "size", "-size", "created_at", "-created_at",
        ),
        required=False,
        default="-created_at",
    )
    page = serializers.IntegerField(min_value=1, max_value=100_000, required=False, default=1)
    page_size = serializers.ChoiceField(choices=(25, 50, 100), required=False, default=25)


class DocumentFileSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    document_id = serializers.SerializerMethodField()
    document_title = serializers.CharField(source="file_document_title")
    source = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    filename = serializers.CharField(source="original_filename")
    kind = serializers.SerializerMethodField()
    version = serializers.IntegerField(source="version_number", allow_null=True)
    media_type = serializers.CharField()
    size = serializers.IntegerField()
    checksum = serializers.CharField()
    created_at = serializers.DateTimeField()

    @extend_schema_field(serializers.CharField())
    def get_kind(self, obj):  # type: ignore[no-untyped-def]
        return "primary" if obj.purpose == DocumentAttachmentPurpose.PRIMARY_FILE else "attachment"

    @extend_schema_field(serializers.UUIDField())
    def get_document_id(self, obj):  # type: ignore[no-untyped-def]
        return obj.document.entity_id if obj.document_id else obj.owner_content_id

    @extend_schema_field(serializers.ChoiceField(choices=("legacy", "repository")))
    def get_source(self, obj):  # type: ignore[no-untyped-def]
        return "repository" if getattr(obj, "repository_authoritative", False) or not obj.document_id else "legacy"

    @extend_schema_field(serializers.CharField())
    def get_download_url(self, obj):  # type: ignore[no-untyped-def]
        workspace = self.context["workspace"]
        if obj.document_id and not getattr(obj, "repository_authoritative", False):
            route = (
                "organization-document-attachment-download"
                if workspace.organization
                else "msp-document-attachment-download"
            )
            kwargs = {"document_entity_id": obj.document.entity_id, "attachment_entity_id": obj.entity_id}
        else:
            route = (
                "organization-content-document-attachment-download"
                if workspace.organization
                else "msp-content-document-attachment-download"
            )
            kwargs = {"content_id": obj.owner_content_id, "attachment_entity_id": obj.entity_id}
        if workspace.organization:
            kwargs["organization_entity_id"] = workspace.organization.entity_id
        return reverse(route, kwargs=kwargs)


class DocumentFileResultSerializer(serializers.Serializer):
    results = DocumentFileSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()
