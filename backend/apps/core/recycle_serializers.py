from rest_framework import serializers

from .recycle_bin import RecoverableRecordType


class RecycleBinQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")
    record_type = serializers.ChoiceField(
        choices=(("", "All"), *((value.value, value.value) for value in RecoverableRecordType)),
        required=False,
        allow_blank=True,
        default="",
    )
    page = serializers.IntegerField(min_value=1, max_value=100, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=50, required=False, default=25)


class RecycleBinItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    record_type = serializers.ChoiceField(choices=tuple((value.value, value.value) for value in RecoverableRecordType))
    label = serializers.CharField()
    archived_at = serializers.DateTimeField()
    workspace_kind = serializers.ChoiceField(choices=("msp", "organization"))
    workspace_id = serializers.UUIDField()
    workspace_name = serializers.CharField()
    cascade_count = serializers.IntegerField(min_value=1)
    can_restore = serializers.BooleanField()


class RecycleBinResultSerializer(serializers.Serializer):
    results = RecycleBinItemSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
