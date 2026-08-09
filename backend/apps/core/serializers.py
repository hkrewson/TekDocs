from typing import cast
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    Document,
    LocationKind,
    Organization,
    OrganizationAccessMode,
    OrganizationKind,
    PersonAssociationKind,
    Site,
)


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
    access_mode = serializers.ChoiceField(choices=OrganizationAccessMode.choices)
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


class LocationWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    kind = serializers.ChoiceField(choices=LocationKind.choices)
    code = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        for field in ("code",):
            value = attrs.get(field)
            if isinstance(value, str) and any(ord(character) < 32 for character in value):
                raise serializers.ValidationError({field: "Control characters are not allowed."})
        return attrs


class LocationSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    site_id = serializers.UUIDField(source="site.entity_id")
    parent_id = serializers.UUIDField(source="parent.entity_id", allow_null=True)
    name = serializers.CharField(source="entity.display_name")
    kind = serializers.ChoiceField(choices=LocationKind.choices)
    code = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class SiteWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    code = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)
    address_line_1 = serializers.CharField(max_length=240, required=False, allow_blank=True, trim_whitespace=True)
    address_line_2 = serializers.CharField(max_length=240, required=False, allow_blank=True, trim_whitespace=True)
    city = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    region = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    postal_code = serializers.CharField(max_length=32, required=False, allow_blank=True, trim_whitespace=True)
    country_code = serializers.RegexField(
        r"^[A-Za-z]{2}$",
        max_length=2,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    timezone = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        for field, value in attrs.items():
            if isinstance(value, str) and any(ord(character) < 32 for character in value):
                raise serializers.ValidationError({field: "Control characters are not allowed."})
        if "country_code" in attrs:
            attrs["country_code"] = attrs["country_code"].upper()
        timezone = attrs.get("timezone", "")
        if timezone:
            try:
                ZoneInfo(timezone)
            except ZoneInfoNotFoundError as exc:
                raise serializers.ValidationError({"timezone": "Use a valid IANA timezone name."}) from exc
        return attrs


class SiteSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    organization_id = serializers.UUIDField(source="organization.entity_id", allow_null=True)
    name = serializers.CharField(source="entity.display_name")
    code = serializers.CharField()
    address_line_1 = serializers.CharField()
    address_line_2 = serializers.CharField()
    city = serializers.CharField()
    region = serializers.CharField()
    postal_code = serializers.CharField()
    country_code = serializers.CharField()
    timezone = serializers.CharField()
    phone = serializers.CharField()
    locations = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    @extend_schema_field(LocationSerializer(many=True))
    def get_locations(self, site: Site) -> list[dict[str, object]]:
        records = getattr(site, "active_locations", ())
        return cast(list[dict[str, object]], LocationSerializer(records, many=True).data)


class SiteQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True, default="")


class SiteResultSerializer(serializers.Serializer):
    results = SiteSerializer(many=True)
    count = serializers.IntegerField()


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
    site_id = serializers.UUIDField(required=False, allow_null=True)
    structured_location_id = serializers.UUIDField(required=False, allow_null=True)
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
    site_id = serializers.UUIDField(source="site.entity_id", allow_null=True)
    structured_location_id = serializers.UUIDField(source="structured_location.entity_id", allow_null=True)
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


class DocumentWriteSerializer(serializers.Serializer):
    title = serializers.CharField(min_length=1, max_length=240, trim_whitespace=True, validators=[_clean_name])
    markdown = serializers.CharField(required=False, allow_blank=True, max_length=1_000_000)


class DocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    title = serializers.CharField(source="entity.display_name")
    owner_kind = serializers.SerializerMethodField()
    owner_organization_id = serializers.UUIDField(source="organization.entity_id", allow_null=True)
    owner_organization_name = serializers.CharField(source="organization.entity.display_name", allow_null=True)
    is_reference = serializers.SerializerMethodField()
    markdown = serializers.SerializerMethodField()
    block_id = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_owner_kind(self, obj: Document) -> str:
        return "organization" if obj.organization_id else "msp"

    def get_is_reference(self, obj: Document) -> bool:
        workspace_organization_id = self.context.get("workspace_organization_id")
        return workspace_organization_id is not None and obj.organization_id is None

    def _placement(self, obj: Document):  # type: ignore[no-untyped-def]
        placements = getattr(obj, "active_placements", ())
        return placements[0] if placements else None

    def get_markdown(self, obj: Document) -> str:
        placement = self._placement(obj)
        return placement.block.markdown if placement is not None else ""

    def get_block_id(self, obj: Document) -> UUID | None:
        placement = self._placement(obj)
        return placement.block.entity_id if placement is not None else None


class DocumentResultSerializer(serializers.Serializer):
    results = DocumentSerializer(many=True)
    count = serializers.IntegerField()


class DocumentationReferenceWriteSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()


class DocumentationReferenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    organization_id = serializers.UUIDField(source="organization.entity_id")
    organization_name = serializers.CharField(source="organization.entity.display_name")
    created_at = serializers.DateTimeField()
