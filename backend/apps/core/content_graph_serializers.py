from rest_framework import serializers


class ContentGraphRebuildSerializer(serializers.Serializer):
    force = serializers.BooleanField(default=False)


class ContentGraphLinkSerializer(serializers.Serializer):
    target_id = serializers.UUIDField()
    fragment = serializers.CharField(allow_null=True)
    label = serializers.CharField(allow_null=True)
    resolved = serializers.BooleanField()


class ContentGraphFindingSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.CharField()
    detail = serializers.DictField()


class ContentGraphNodeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField()
    path = serializers.CharField()
    markdown = serializers.CharField()
    properties = serializers.DictField()
    taxonomies = serializers.DictField()
    topic = serializers.DictField(allow_null=True)
    outgoing_links = ContentGraphLinkSerializer(many=True)
    backlinks = serializers.ListField(child=serializers.UUIDField())
    findings = ContentGraphFindingSerializer(many=True)


class ContentIndexAttemptSerializer(serializers.Serializer):
    commit = serializers.CharField()
    status = serializers.CharField()
    diagnostics = serializers.ListField(child=serializers.DictField())
    projection_digest = serializers.CharField(allow_null=True)


class ContentGraphSerializer(serializers.Serializer):
    accepted_commit = serializers.CharField(allow_null=True)
    indexed_commit = serializers.CharField(allow_null=True)
    nodes = ContentGraphNodeSerializer(many=True)
    latest_attempt = ContentIndexAttemptSerializer(allow_null=True)
