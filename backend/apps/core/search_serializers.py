from rest_framework import serializers

SEARCH_RESULT_TYPES = (
    "organization",
    "person",
    "site",
    "location",
    "document",
    "file",
    "asset",
    "product",
    "model",
    "license",
    "service",
    "credential_reference",
    "domain",
    "certificate",
    "network",
    "data_flow",
    "external_ticket",
)


class UnifiedWorkspaceSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=80, trim_whitespace=True)
    result_type = serializers.ChoiceField(choices=SEARCH_RESULT_TYPES, required=False, allow_blank=True, default="")
    page = serializers.IntegerField(min_value=1, max_value=100, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=25, required=False, default=15)


class UnifiedWorkspaceSearchHitSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    result_type = serializers.ChoiceField(choices=SEARCH_RESULT_TYPES)
    entity_type = serializers.CharField()
    title = serializers.CharField()
    excerpt = serializers.CharField(allow_blank=True)
    workspace_label = serializers.CharField()
    target = serializers.CharField()
    score = serializers.IntegerField(min_value=0)
    updated_at = serializers.DateTimeField()
    review_state = serializers.CharField(allow_null=True)


class UnifiedWorkspaceSearchFacetSerializer(serializers.Serializer):
    value = serializers.ChoiceField(choices=SEARCH_RESULT_TYPES)
    label = serializers.CharField()
    count = serializers.IntegerField(min_value=0)


class UnifiedWorkspaceSearchResultSerializer(serializers.Serializer):
    results = UnifiedWorkspaceSearchHitSerializer(many=True)
    facets = UnifiedWorkspaceSearchFacetSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    truncated = serializers.BooleanField()
