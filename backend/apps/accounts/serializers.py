from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Invitation, User


class OwnerBootstrapSerializer(serializers.Serializer):
    tenant_name = serializers.CharField(max_length=160)
    owner_email = serializers.EmailField(max_length=254)
    owner_display_name = serializers.CharField(max_length=160)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        candidate = User(email=attrs["owner_email"], display_name=attrs["owner_display_name"])
        try:
            password_validation.validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


class BootstrapStatusSerializer(serializers.Serializer):
    bootstrap_required = serializers.BooleanField()


class BootstrapTenantResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class BootstrapOwnerResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()


class OwnerBootstrapResultSerializer(serializers.Serializer):
    tenant = BootstrapTenantResultSerializer()
    owner = BootstrapOwnerResultSerializer()


class AuthenticatedUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    display_name = serializers.CharField()


class AuthenticatedContextSerializer(serializers.Serializer):
    user = AuthenticatedUserSerializer()
    tenant = BootstrapTenantResultSerializer()
    role = serializers.CharField()
    permissions = serializers.ListField(child=serializers.CharField())
    surface = serializers.ChoiceField(choices=("msp", "client_portal"))
    organization = serializers.DictField(allow_null=True)


class ProfileUpdateSerializer(serializers.Serializer):
    display_name = serializers.CharField(min_length=1, max_length=160, trim_whitespace=True)

    def validate_display_name(self, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise serializers.ValidationError("Display name cannot contain control characters.")
        return value


class OidcProviderSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()


class OidcProviderListSerializer(serializers.Serializer):
    providers = OidcProviderSerializer(many=True)


class InvitationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class InvitationAcceptanceSerializer(serializers.Serializer):
    token = serializers.CharField(required=False, default="", trim_whitespace=False, write_only=True)
    display_name = serializers.CharField(max_length=160)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class InvitationSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()

    def get_organization(self, invitation: Invitation) -> dict[str, str] | None:
        organization = invitation.organization
        if organization is None:
            return None
        return {
            "id": str(organization.entity_id),
            "name": organization.entity.display_name,
        }

    class Meta:
        model = Invitation
        fields = (
            "id",
            "email",
            "role",
            "organization",
            "state",
            "expires_at",
            "last_sent_at",
            "last_delivery_failed_at",
            "delivery_attempts",
            "send_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
