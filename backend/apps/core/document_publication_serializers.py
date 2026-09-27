"""API serializers for retained document publications and portal projections."""

from uuid import UUID

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    DocumentCategory,
    DocumentPublication,
    DocumentPublicationControlEvent,
    PublicationAudience,
    PublicationRetention,
)


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
