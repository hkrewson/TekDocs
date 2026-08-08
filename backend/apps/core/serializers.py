from urllib.parse import urlsplit

from rest_framework import serializers

from .models import Organization, OrganizationKind, PersonAssociationKind


def _clean_name(value: str) -> str:
    if any(ord(character) < 32 for character in value):
        raise serializers.ValidationError("Name cannot contain control characters.")
    return value


class OrganizationWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    legal_name = serializers.CharField(max_length=240, trim_whitespace=True, required=False, allow_blank=True)
    website = serializers.URLField(max_length=500, required=False, allow_blank=True)
    classifications = serializers.ListField(
        child=serializers.ChoiceField(choices=OrganizationKind.choices),
        min_length=1,
        max_length=len(OrganizationKind),
        allow_empty=False,
    )

    def validate_classifications(self, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Classifications must be unique.")
        return value

    def validate_website(self, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"}:
            raise serializers.ValidationError("Website must use HTTP or HTTPS.")
        if parsed.username is not None or parsed.password is not None:
            raise serializers.ValidationError("Website must not contain embedded credentials.")
        return value


class OrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    legal_name = serializers.CharField()
    website = serializers.URLField()
    classifications = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_classifications(self, organization: Organization) -> list[str]:
        return sorted(classification.kind for classification in organization.classifications.all())


class WorkspaceContextSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("msp", "organization"))
    id = serializers.UUIDField()
    name = serializers.CharField()
    classifications = serializers.ListField(child=serializers.ChoiceField(choices=OrganizationKind.choices))
    capabilities = serializers.ListField(child=serializers.CharField())
    organization = OrganizationSerializer(allow_null=True)


class WorkspaceSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")
    classification = serializers.ChoiceField(
        choices=OrganizationKind.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    page = serializers.IntegerField(min_value=1, max_value=100, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=25, required=False, default=15)


class WorkspaceOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    classifications = serializers.ListField(child=serializers.ChoiceField(choices=OrganizationKind.choices))
    capabilities = serializers.ListField(child=serializers.CharField())


class WorkspaceSearchResultSerializer(serializers.Serializer):
    results = WorkspaceOptionSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()


PERSON_SORT_FIELDS = (
    "full_name",
    "preferred_name",
    "kind",
    "role",
    "responsibility",
    "location",
    "office",
    "phone",
    "email",
)
PERSON_FILTER_FIELDS = PERSON_SORT_FIELDS[1:]


class PersonWriteSerializer(serializers.Serializer):
    full_name = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    preferred_name = serializers.CharField(max_length=160, required=False, allow_blank=True, trim_whitespace=True)
    kind = serializers.ChoiceField(choices=PersonAssociationKind.choices)
    role = serializers.CharField(max_length=160, required=False, allow_blank=True, trim_whitespace=True)
    responsibility = serializers.CharField(max_length=240, required=False, allow_blank=True, trim_whitespace=True)
    location = serializers.CharField(max_length=160, required=False, allow_blank=True, trim_whitespace=True)
    office = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        for field, value in attrs.items():
            if isinstance(value, str) and any(ord(character) < 32 for character in value):
                raise serializers.ValidationError({field: "Control characters are not allowed."})
        return attrs


class PersonSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="person.entity_id")
    association_id = serializers.UUIDField(source="id")
    organization_id = serializers.UUIDField(source="organization.entity_id", allow_null=True)
    full_name = serializers.CharField(source="person.entity.display_name")
    preferred_name = serializers.CharField(source="person.preferred_name")
    kind = serializers.ChoiceField(choices=PersonAssociationKind.choices)
    role = serializers.CharField()
    responsibility = serializers.CharField()
    location = serializers.CharField()
    office = serializers.CharField()
    phone = serializers.CharField(source="person.phone")
    email = serializers.EmailField(source="person.email")
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class PeopleQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")
    filter_field = serializers.ChoiceField(
        choices=PERSON_FILTER_FIELDS,
        required=False,
        allow_blank=True,
        default="",
    )
    filter_value = serializers.CharField(
        max_length=80,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )
    ordering = serializers.ChoiceField(
        choices=tuple(PERSON_SORT_FIELDS) + tuple(f"-{field}" for field in PERSON_SORT_FIELDS),
        required=False,
        default="full_name",
    )
    page = serializers.IntegerField(min_value=1, max_value=1000, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=50, required=False, default=25)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if bool(attrs["filter_field"]) != bool(attrs["filter_value"]):
            raise serializers.ValidationError("Filter field and value must be supplied together.")
        return attrs


class PeopleResultSerializer(serializers.Serializer):
    results = PersonSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
