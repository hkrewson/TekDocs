from __future__ import annotations

from typing import Any, cast

from rest_framework import serializers

from .custom_fields import (
    SUPPORTED_ENTITY_TYPES,
    CustomFieldValueError,
    latest_version,
    validate_custom_field_value,
)
from .models import CustomFieldDefinition, CustomFieldType


def _clean_text(value: str) -> str:
    if any(ord(character) < 32 for character in value):
        raise serializers.ValidationError("Control characters are not allowed.")
    return value


class CustomFieldVersionWriteSerializer(serializers.Serializer):
    label = serializers.CharField(min_length=1, max_length=160, trim_whitespace=True, validators=[_clean_text])
    description = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        validators=[_clean_text],
    )
    required = serializers.BooleanField(required=False, default=False)
    field_type = serializers.ChoiceField(choices=CustomFieldType.choices)
    display_order = serializers.IntegerField(min_value=-1000, max_value=1000, required=False, default=0)
    options = serializers.ListField(
        child=serializers.CharField(min_length=1, max_length=160, trim_whitespace=True, validators=[_clean_text]),
        max_length=50,
        allow_empty=True,
        required=False,
        default=list,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        options = attrs["options"]
        field_type = attrs["field_type"]
        if len(options) != len(set(options)):
            raise serializers.ValidationError({"options": "Choices must be unique."})
        if field_type in {CustomFieldType.CHOICE, CustomFieldType.MULTI_CHOICE} and not options:
            raise serializers.ValidationError({"options": "Add at least one choice."})
        if field_type not in {CustomFieldType.CHOICE, CustomFieldType.MULTI_CHOICE} and options:
            raise serializers.ValidationError({"options": "Only choice fields accept options."})
        return attrs


class CustomFieldDefinitionWriteSerializer(CustomFieldVersionWriteSerializer):
    key = serializers.RegexField(
        r"^[a-z][a-z0-9_-]*$",
        min_length=1,
        max_length=80,
        help_text="Stable lowercase key beginning with a letter.",
    )
    entity_type = serializers.ChoiceField(choices=SUPPORTED_ENTITY_TYPES)


class CustomFieldVersionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    label = serializers.CharField()
    description = serializers.CharField()
    required = serializers.BooleanField()
    field_type = serializers.ChoiceField(choices=CustomFieldType.choices)
    schema = serializers.JSONField()
    display_order = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class CustomFieldDefinitionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    key = serializers.CharField()
    entity_type = serializers.CharField()
    owner = serializers.SerializerMethodField()
    organization_id = serializers.SerializerMethodField()
    inherited = serializers.SerializerMethodField()
    archived = serializers.SerializerMethodField()
    current_version = serializers.SerializerMethodField()
    versions = CustomFieldVersionSerializer(many=True)

    def get_owner(self, definition: CustomFieldDefinition) -> str:
        return "organization" if definition.organization_id is not None else "msp"

    def get_organization_id(self, definition: CustomFieldDefinition) -> str | None:
        organization = definition.organization if definition.organization_id is not None else None
        return str(organization.entity_id) if organization is not None else None

    def get_inherited(self, definition: CustomFieldDefinition) -> bool:
        organization_id = self.context.get("organization_id")
        return organization_id is not None and definition.organization_id is None

    def get_archived(self, definition: CustomFieldDefinition) -> bool:
        return definition.archived_at is not None

    def get_current_version(self, definition: CustomFieldDefinition) -> dict[str, Any]:
        return cast(dict[str, Any], CustomFieldVersionSerializer(latest_version(definition)).data)


class CustomFieldDefinitionResultSerializer(serializers.Serializer):
    results = CustomFieldDefinitionSerializer(many=True)
    count = serializers.IntegerField()


class MigrationImpactSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    compatible = serializers.IntegerField()
    incompatible = serializers.IntegerField()


class CustomFieldDefinitionVersionResultSerializer(serializers.Serializer):
    definition = CustomFieldDefinitionSerializer()
    migration_impact = MigrationImpactSerializer()


class CustomFieldValueWriteSerializer(serializers.Serializer):
    value = serializers.JSONField()


class EntityCustomFieldSerializer(serializers.Serializer):
    definition = CustomFieldDefinitionSerializer()
    has_value = serializers.BooleanField()
    value = serializers.JSONField(allow_null=True)
    value_version_id = serializers.UUIDField(allow_null=True)
    value_version = serializers.IntegerField(allow_null=True)
    is_current = serializers.BooleanField()
    valid_for_current = serializers.BooleanField()


class EntityCustomFieldResultSerializer(serializers.Serializer):
    entity_id = serializers.UUIDField()
    entity_type = serializers.CharField()
    fields = EntityCustomFieldSerializer(many=True)


def serialize_entity_custom_fields(*, entity: Any, definitions: list[CustomFieldDefinition]) -> dict[str, Any]:
    fields = []
    for definition in definitions:
        current = latest_version(definition)
        envelope = entity.custom_fields.get(str(definition.id))
        has_value = isinstance(envelope, dict) and "value" in envelope
        value = envelope.get("value") if has_value else None
        value_version_id = envelope.get("definition_version_id") if has_value else None
        value_version = envelope.get("version") if has_value else None
        valid_for_current = not has_value
        if has_value:
            try:
                validate_custom_field_value(schema=current.schema, value=value)
                valid_for_current = True
            except CustomFieldValueError:
                valid_for_current = False
        fields.append(
            {
                "definition": definition,
                "has_value": has_value,
                "value": value,
                "value_version_id": value_version_id,
                "value_version": value_version,
                "is_current": has_value and str(current.id) == value_version_id,
                "valid_for_current": valid_for_current,
            }
        )
    return {"entity_id": entity.id, "entity_type": entity.entity_type, "fields": fields}
