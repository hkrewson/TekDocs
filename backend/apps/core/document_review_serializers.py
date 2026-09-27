"""API serializers for document review requests and decisions."""

from rest_framework import serializers

from .models import DocumentReviewState


class DocumentReviewRequestWriteSerializer(serializers.Serializer):
    reviewer_id = serializers.UUIDField()
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class DocumentReviewDecisionWriteSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=(DocumentReviewState.APPROVED, DocumentReviewState.CHANGES_REQUESTED)
    )
    note = serializers.CharField(max_length=500, allow_blank=False)
