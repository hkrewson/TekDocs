"""API serializers for document template instantiation and rollout."""

from rest_framework import serializers

from .models import DocumentCategory


def _clean_name(value: str) -> str:
    if any(ord(character) < 32 for character in value):
        raise serializers.ValidationError("Name cannot contain control characters.")
    return value


class DocumentTemplateInstantiateSerializer(serializers.Serializer):
    source_document_id = serializers.UUIDField()
    title = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    category = serializers.ChoiceField(choices=DocumentCategory.choices)
    expected_source_sha256 = serializers.RegexField(r"^[0-9a-f]{64}$", required=False)
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
    expected_available_revision = serializers.IntegerField(min_value=1, required=False)
    expected_base = serializers.RegexField(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$", required=False)
    expected_composition = serializers.RegexField(r"^[0-9a-f]{64}$", required=False)
    placement_rules = serializers.DictField(
        child=serializers.ChoiceField(choices=("copy", "live", "pinned")),
        required=False,
        default=dict,
    )


class DocumentTemplateReusedSectionSerializer(serializers.Serializer):
    placement_id = serializers.UUIDField()
    title = serializers.CharField()
    mode = serializers.ChoiceField(choices=("live", "pinned"))


class DocumentTemplateDetachSerializer(serializers.Serializer):
    expected_base = serializers.RegexField(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    expected_composition = serializers.RegexField(r"^[0-9a-f]{64}$")
    expected_applied_revision_id = serializers.UUIDField()


class DocumentTemplateDetachRequestSerializer(serializers.Serializer):
    expected_base = serializers.RegexField(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$", required=False)
    expected_composition = serializers.RegexField(r"^[0-9a-f]{64}$", required=False)
    expected_applied_revision_id = serializers.UUIDField(required=False)


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
    base_commit = serializers.CharField(required=False)
    composition_digest = serializers.CharField(required=False)
    reused_sections = DocumentTemplateReusedSectionSerializer(many=True, required=False)
