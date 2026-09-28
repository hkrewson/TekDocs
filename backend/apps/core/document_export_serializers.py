"""API query serializers for live document and retained publication exports."""

from rest_framework import serializers

from .document_exports import EXPORT_FORMATS


class DocumentExportQuerySerializer(serializers.Serializer):
    export_format = serializers.ChoiceField(choices=sorted(EXPORT_FORMATS), default="md")
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        max_length=50,
    )

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        attachment_ids = attrs["attachment_ids"]
        if attrs["export_format"] != "bundle" and attachment_ids:
            raise serializers.ValidationError("Files may be selected only for a portable bundle.")
        if len(set(attachment_ids)) != len(attachment_ids):
            raise serializers.ValidationError("Each selected file may appear only once.")
        return attrs


class DocumentPublicationExportQuerySerializer(serializers.Serializer):
    export_format = serializers.ChoiceField(choices=sorted(EXPORT_FORMATS - {"bundle"}), default="md")
