from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User


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
