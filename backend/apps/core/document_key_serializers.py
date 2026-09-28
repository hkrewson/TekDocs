"""API serializers for document key bindings, reports, and workspace browsing."""

from collections.abc import Mapping
from uuid import UUID

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .document_key_fields import addressable_fields
from .document_keys import BINDING_NAME_PATTERN
from .models import DocumentKeyBinding

#: Rejecting a name is common — an author types a capitalised word before knowing
#: the grammar — so the refusal states the rule rather than reporting a pattern
#: mismatch.
BINDING_NAME_HELP = (
    "A binding name uses lowercase letters, digits and underscores, and starts with a "
    "letter. For example: subject, primary_switch."
)


class KeyBindingWriteSerializer(serializers.Serializer):
    name = serializers.RegexField(BINDING_NAME_PATTERN, max_length=40, error_messages={"invalid": BINDING_NAME_HELP})
    target_entity_id = serializers.UUIDField()


class BoundDocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()


class KeyBindingResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    target_entity_id = serializers.UUIDField(source="target_entity.id")
    target_display_name = serializers.CharField(source="target_entity.display_name")
    target_entity_type = serializers.CharField(source="target_entity.entity_type")
    addressable_fields = serializers.SerializerMethodField()
    also_bound_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_addressable_fields(self, binding: DocumentKeyBinding) -> list[str]:
        """Every key path this binding can resolve, so an author need not guess."""
        return addressable_fields(binding.target_entity.entity_type)

    @extend_schema_field(BoundDocumentSerializer(many=True))
    def get_also_bound_by(self, binding: DocumentKeyBinding) -> list[dict[str, str]]:
        """Other documents that resolve values from the same record.

        This is where-used, shown where the decision is made. Once documentation
        derives from inventory, editing one asset silently rewrites every document
        that quotes it, so the blast radius has to be visible while binding rather
        than discovered afterwards.
        """
        usage: Mapping[UUID, list[dict[str, str]]] = self.context.get("also_bound_by", {})
        return usage.get(binding.target_entity_id, [])


class KeyBindingListSerializer(serializers.Serializer):
    results = KeyBindingResultSerializer(many=True)
    count = serializers.IntegerField()
    #: The record kinds a binding may target. The authoring surface reads this
    #: instead of carrying its own registry, so adding a resolvable kind remains a
    #: single server change.
    addressable_entity_types = serializers.ListField(child=serializers.CharField())


class DocumentKeySerializer(serializers.Serializer):
    expression = serializers.CharField()
    state = serializers.CharField()
    label = serializers.CharField()
    reason = serializers.CharField(allow_null=True)


class DocumentKeyReportSerializer(serializers.Serializer):
    results = DocumentKeySerializer(many=True)
    count = serializers.IntegerField()
    unresolved_count = serializers.IntegerField()


class WorkspaceKeyBindingSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    document_id = serializers.UUIDField(source="document.entity_id")
    document_title = serializers.CharField(source="document.entity.display_name")
    target_entity_id = serializers.UUIDField(source="target_entity.id")
    target_display_name = serializers.CharField(source="target_entity.display_name")
    target_entity_type = serializers.CharField(source="target_entity.entity_type")


class WorkspaceKeyBindingListSerializer(serializers.Serializer):
    results = WorkspaceKeyBindingSerializer(many=True)
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
