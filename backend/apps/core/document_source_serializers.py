"""API serializers for monitored document sources and observations."""

from difflib import unified_diff

from rest_framework import serializers

from .document_sources import validate_remote_source_url
from .models import DocumentRemoteObservation, DocumentSourceKind


class RemoteSourceWriteSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=500)
    source_kind = serializers.ChoiceField(choices=DocumentSourceKind.values, default=DocumentSourceKind.AUTO)
    enabled = serializers.BooleanField(default=True)
    check_interval_minutes = serializers.IntegerField(min_value=15, max_value=10080, default=1440)

    def validate_url(self, value: str) -> str:
        return validate_remote_source_url(value)


class RemoteSourceResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    url = serializers.URLField()
    source_kind = serializers.CharField()
    enabled = serializers.BooleanField()
    check_interval_minutes = serializers.IntegerField()
    next_check_at = serializers.DateTimeField()
    last_checked_at = serializers.DateTimeField(allow_null=True)
    last_applied_observation_id = serializers.UUIDField(allow_null=True)


class RemoteObservationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    state = serializers.CharField()
    status_code = serializers.IntegerField(allow_null=True)
    content_type = serializers.CharField()
    content_digest = serializers.CharField()
    error_code = serializers.CharField()
    fetched_at = serializers.DateTimeField()
    canonical_markdown = serializers.CharField()
    diff = serializers.SerializerMethodField()

    def get_diff(self, observation: DocumentRemoteObservation) -> str:
        source = observation.source
        prior = source.last_applied_observation
        before = prior.canonical_markdown if prior else ""
        return "".join(
            unified_diff(
                before.splitlines(keepends=True),
                observation.canonical_markdown.splitlines(keepends=True),
                fromfile="last-applied" if prior else "empty",
                tofile="observed",
            )
        )


class RemoteObservationListSerializer(serializers.Serializer):
    results = RemoteObservationSerializer(many=True)
    count = serializers.IntegerField()
