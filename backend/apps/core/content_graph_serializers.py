from rest_framework import serializers


class ContentGraphRebuildSerializer(serializers.Serializer):
    force = serializers.BooleanField(default=False)


class ContentGraphQuerySerializer(serializers.Serializer):
    audience = serializers.ChoiceField(choices=("all", "msp_internal", "client_visible"), default="all")


class ContentGraphLinkSerializer(serializers.Serializer):
    target_id = serializers.UUIDField()
    fragment = serializers.CharField(allow_null=True)
    label = serializers.CharField(allow_null=True)
    resolved = serializers.BooleanField()


class ContentGraphFindingSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.CharField()
    detail = serializers.DictField()


class ContentIncludeSerializer(serializers.Serializer):
    target_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=("live", "pinned"))
    audience = serializers.ChoiceField(choices=("shared", "msp_internal", "client_visible"))
    pinned_commit = serializers.CharField(allow_null=True)
    resolved_commit = serializers.CharField()
    resolved_digest = serializers.CharField()


class ContentTemplateSourceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    commit = serializers.CharField()
    pinned_digest = serializers.CharField()
    current_digest = serializers.CharField(allow_null=True)
    title = serializers.CharField()
    state = serializers.ChoiceField(choices=("current", "changed", "missing"))
    change_preview = serializers.CharField(allow_blank=True)


class ContentDerivedFromSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    commit = serializers.CharField()


class ContentGraphNodeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField()
    path = serializers.CharField()
    markdown = serializers.CharField()
    properties = serializers.DictField()
    taxonomies = serializers.DictField()
    topic = serializers.DictField(allow_null=True)
    composition = serializers.DictField(allow_null=True)
    derived_from = ContentDerivedFromSerializer(allow_null=True)
    includes = ContentIncludeSerializer(many=True)
    included_by = serializers.ListField(child=serializers.UUIDField())
    template_sources = ContentTemplateSourceSerializer(many=True)
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
