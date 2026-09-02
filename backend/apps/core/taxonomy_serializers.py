from rest_framework import serializers

from .models import TaxonomyBinding, TaxonomyTermStatus


class TaxonomyTermWriteSerializer(serializers.Serializer):
    stable_key = serializers.SlugField(max_length=80)
    label = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    parent_key = serializers.SlugField(max_length=80, required=False, allow_blank=True, default="")
    aliases = serializers.ListField(
        child=serializers.CharField(max_length=120), max_length=20, required=False, default=list
    )
    status = serializers.ChoiceField(
        choices=TaxonomyTermStatus.choices, required=False, default=TaxonomyTermStatus.ACTIVE
    )
    replacement_key = serializers.SlugField(max_length=80, required=False, allow_blank=True, default="")
    sort_order = serializers.IntegerField(min_value=0, max_value=100000, required=False, default=0)


class TaxonomyVersionWriteSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    allow_local_terms = serializers.BooleanField(required=False, default=False)
    terms = TaxonomyTermWriteSerializer(many=True, allow_empty=False, max_length=500)


class TaxonomyCreateSerializer(TaxonomyVersionWriteSerializer):
    key = serializers.SlugField(max_length=80)
    binding = serializers.ChoiceField(choices=TaxonomyBinding.choices)


class TaxonomyTermSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    stable_key = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    parent_key = serializers.CharField()
    aliases = serializers.ListField(child=serializers.CharField())
    status = serializers.ChoiceField(choices=TaxonomyTermStatus.choices)
    replacement_key = serializers.CharField()
    sort_order = serializers.IntegerField()
    local = serializers.BooleanField(required=False, default=False)
    impact = serializers.DictField(child=serializers.IntegerField())


class OrganizationTaxonomyTermWriteSerializer(serializers.Serializer):
    stable_key = serializers.SlugField(max_length=80)
    label = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    aliases = serializers.ListField(
        child=serializers.CharField(max_length=120), max_length=20, required=False, default=list
    )


class TaxonomyCurrentVersionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    label = serializers.CharField()
    description = serializers.CharField()
    allow_local_terms = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    terms = TaxonomyTermSerializer(many=True)


class TaxonomyVersionSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    label = serializers.CharField()
    created_at = serializers.DateTimeField()


class TaxonomyImpactSerializer(serializers.Serializer):
    documents = serializers.IntegerField()
    templates = serializers.IntegerField()


class TaxonomySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    key = serializers.CharField()
    binding = serializers.ChoiceField(choices=TaxonomyBinding.choices)
    archived = serializers.BooleanField()
    current_version = TaxonomyCurrentVersionSerializer()
    versions = TaxonomyVersionSummarySerializer(many=True)
    impact = TaxonomyImpactSerializer()


class TaxonomyResultSerializer(serializers.Serializer):
    results = TaxonomySerializer(many=True)
    count = serializers.IntegerField()


class TaxonomyMigrationWriteSerializer(serializers.Serializer):
    apply = serializers.BooleanField(required=False, default=False)


class TaxonomyMigrationRowSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    document_title = serializers.CharField()
    tag = serializers.CharField()
    status = serializers.ChoiceField(choices=("matched", "unmatched", "ambiguous"))
    term_id = serializers.UUIDField(allow_null=True)
    term_label = serializers.CharField(allow_null=True)


class TaxonomyMigrationSerializer(serializers.Serializer):
    counts = serializers.DictField(child=serializers.IntegerField())
    rows = TaxonomyMigrationRowSerializer(many=True)
