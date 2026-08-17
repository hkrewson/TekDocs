from rest_framework import serializers

from .models import EntityLinkType, EntityVisibility
from .relationships import SEARCHABLE_ENTITY_TYPES

GRAPH_FAMILIES = ("network", "asset", "document")


class EntitySearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")
    entity_type = serializers.ChoiceField(
        choices=SEARCHABLE_ENTITY_TYPES,
        required=False,
        allow_blank=True,
        default="",
    )
    page = serializers.IntegerField(min_value=1, max_value=1000, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=25, required=False, default=15)


class EntityReferenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    entity_type = serializers.ChoiceField(choices=SEARCHABLE_ENTITY_TYPES)
    visibility = serializers.ChoiceField(choices=EntityVisibility.choices)
    workspace_label = serializers.CharField()
    eligible_link_types = serializers.ListField(child=serializers.ChoiceField(choices=EntityLinkType.choices))


class EntitySearchResultSerializer(serializers.Serializer):
    results = EntityReferenceSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()


class EntityLinkTypeSerializer(serializers.Serializer):
    value = serializers.ChoiceField(choices=EntityLinkType.choices)
    forward_label = serializers.CharField()
    inverse_label = serializers.CharField()
    symmetric = serializers.BooleanField()
    target_types = serializers.ListField(child=serializers.CharField())


class EntityLinkWriteSerializer(serializers.Serializer):
    target_id = serializers.UUIDField()
    link_type = serializers.ChoiceField(choices=EntityLinkType.choices)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        submitted = set(self.initial_data) if isinstance(self.initial_data, dict) else set()
        unexpected = submitted - {"target_id", "link_type"}
        if unexpected:
            raise serializers.ValidationError("Only target_id and link_type are accepted.")
        return attrs


class EntityRelationshipSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    link_type = serializers.ChoiceField(choices=EntityLinkType.choices)
    label = serializers.CharField()
    direction = serializers.ChoiceField(choices=("outgoing", "incoming"))
    source_id = serializers.UUIDField()
    target_id = serializers.UUIDField()
    related_entity = EntityReferenceSerializer()
    created_at = serializers.DateTimeField()


class EntityRelationshipResultSerializer(serializers.Serializer):
    relationships = EntityRelationshipSerializer(many=True)


class RelationshipGraphQuerySerializer(serializers.Serializer):
    family = serializers.ChoiceField(choices=GRAPH_FAMILIES)
    root_entity_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    depth = serializers.IntegerField(min_value=1, max_value=3, required=False, default=1)
    edge_limit = serializers.IntegerField(min_value=1, max_value=200, required=False, default=100)


class RelationshipGraphNodeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField()
    entity_type = serializers.CharField()
    visibility = serializers.ChoiceField(choices=EntityVisibility.choices)
    root = serializers.BooleanField()


class RelationshipGraphEdgeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source = serializers.UUIDField()
    target = serializers.UUIDField()
    link_type = serializers.ChoiceField(choices=EntityLinkType.choices)
    label = serializers.CharField()
    symmetric = serializers.BooleanField()


class RelationshipGraphSerializer(serializers.Serializer):
    family = serializers.ChoiceField(choices=GRAPH_FAMILIES)
    root_entity_id = serializers.UUIDField(allow_null=True)
    workspace = serializers.DictField()
    depth = serializers.IntegerField()
    edge_limit = serializers.IntegerField()
    truncated = serializers.BooleanField()
    digest = serializers.RegexField(r"^[0-9a-f]{64}$")
    nodes = RelationshipGraphNodeSerializer(many=True)
    edges = RelationshipGraphEdgeSerializer(many=True)
