from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .collection_pagination import BoundedCollectionQuerySerializer, paginate
from .credential_references import (
    archive_credential_reference,
    create_credential_reference,
    normalize_credential_reference,
    query_references,
    record_credential_reference_open,
    references_for_scope,
    update_credential_reference,
)
from .models import CredentialReference, CredentialReferenceProvider
from .scoping import DataScope
from .workspaces import ResolvedWorkspace, resolve_organization_workspace


class CredentialReferenceWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=240, trim_whitespace=True)
    provider = serializers.ChoiceField(choices=CredentialReferenceProvider.choices)
    reference_url = serializers.CharField(max_length=1000, trim_whitespace=False, write_only=True)

    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        try:
            normalize_credential_reference(attrs["provider"], attrs["reference_url"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"reference_url": exc.messages}) from exc
        return attrs


class CredentialReferenceUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=240, trim_whitespace=True, required=False)
    reference_url = serializers.CharField(max_length=1000, trim_whitespace=False, write_only=True, required=False)

    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)

    def validate_reference_url(self, value: str) -> str:
        try:
            normalize_credential_reference(CredentialReferenceProvider.ONEPASSWORD, value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value


class CredentialReferenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    provider = serializers.ChoiceField(choices=CredentialReferenceProvider.choices)
    provider_label = serializers.CharField()
    updated_at = serializers.DateTimeField()
    can_manage = serializers.BooleanField()
    can_open = serializers.BooleanField()


class CredentialReferenceResultSerializer(serializers.Serializer):
    results = CredentialReferenceSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    can_manage = serializers.BooleanField()


class CredentialReferenceQuerySerializer(BoundedCollectionQuerySerializer):
    q = serializers.CharField(max_length=240, required=False, allow_blank=True, trim_whitespace=True, default="")


def _msp_workspace(request, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    member = require_permission(request.user, permission)
    return ResolvedWorkspace(
        member, "msp", member.tenant.id, member.tenant.name, DataScope.tenant(member.tenant), (), ("credentials",)
    )


def _organization_workspace(request, organization_entity_id: UUID, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = resolve_organization_workspace(request.user, entity_id=organization_entity_id)
    require_permission(request.user, permission, organization=workspace.organization)
    return workspace


def _serialize(
    reference: CredentialReference, *, can_manage: bool, can_open: bool
) -> dict[str, object]:
    return {
        "id": reference.entity_id,
        "title": reference.entity.display_name,
        "provider": reference.provider,
        "provider_label": reference.get_provider_display(),
        "updated_at": reference.updated_at,
        "can_manage": can_manage,
        "can_open": can_open,
    }


def _list(workspace: ResolvedWorkspace, request) -> Response:  # type: ignore[no-untyped-def]
    query = CredentialReferenceQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    values = query.validated_data
    page = paginate(
        query_references(scope=workspace.data_scope, q=values["q"]),
        page=values["page"],
        page_size=values["page_size"],
    )
    can_manage = context_has_permission(
        workspace.member,
        PermissionKey.CREDENTIAL_REFERENCES_MANAGE,
        organization=workspace.organization,
    )
    can_open = context_has_permission(
        workspace.member,
        PermissionKey.CREDENTIAL_REFERENCES_OPEN,
        organization=workspace.organization,
    )
    return Response(
        {
            "results": [_serialize(item, can_manage=can_manage, can_open=can_open) for item in page.records],
            "page": page.page,
            "page_size": page.page_size,
            "count": page.count,
            "has_more": page.has_more,
            "can_manage": can_manage,
        }
    )


def _create(workspace: ResolvedWorkspace, request) -> Response:  # type: ignore[no-untyped-def]
    serializer = CredentialReferenceWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    reference = create_credential_reference(
        tenant=workspace.member.tenant,
        organization=workspace.organization,
        actor_id=request.user.pk,
        **serializer.validated_data,
    )
    return Response(
        _serialize(
            reference,
            can_manage=True,
            can_open=context_has_permission(
                workspace.member,
                PermissionKey.CREDENTIAL_REFERENCES_OPEN,
                organization=workspace.organization,
            ),
        ),
        status=201,
    )


def _get(workspace: ResolvedWorkspace, entity_id: UUID) -> CredentialReference:
    return get_object_or_404(references_for_scope(workspace.data_scope), entity_id=entity_id)


def _update(workspace: ResolvedWorkspace, request, entity_id: UUID) -> Response:  # type: ignore[no-untyped-def]
    reference = _get(workspace, entity_id)
    serializer = CredentialReferenceUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if not serializer.validated_data:
        raise serializers.ValidationError("Provide a title or replacement private link.")
    update_credential_reference(reference=reference, actor_id=request.user.pk, **serializer.validated_data)
    return Response(
        _serialize(
            reference,
            can_manage=True,
            can_open=context_has_permission(
                workspace.member,
                PermissionKey.CREDENTIAL_REFERENCES_OPEN,
                organization=workspace.organization,
            ),
        )
    )


class MSPCredentialReferenceListCreateView(APIView):
    @extend_schema(
        parameters=[CredentialReferenceQuerySerializer], responses={200: CredentialReferenceResultSerializer}
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        return _list(_msp_workspace(request, PermissionKey.CREDENTIAL_REFERENCES_VIEW), request)

    @extend_schema(request=CredentialReferenceWriteSerializer, responses={201: CredentialReferenceSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        return _create(_msp_workspace(request, PermissionKey.CREDENTIAL_REFERENCES_MANAGE), request)


class OrganizationCredentialReferenceListCreateView(APIView):
    @extend_schema(
        parameters=[CredentialReferenceQuerySerializer], responses={200: CredentialReferenceResultSerializer}
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _list(
            _organization_workspace(request, organization_entity_id, PermissionKey.CREDENTIAL_REFERENCES_VIEW), request
        )

    @extend_schema(request=CredentialReferenceWriteSerializer, responses={201: CredentialReferenceSerializer})
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _create(
            _organization_workspace(request, organization_entity_id, PermissionKey.CREDENTIAL_REFERENCES_MANAGE),
            request,
        )


class _CredentialReferenceDetailView(APIView):
    def workspace(self, request, permission: PermissionKey, organization_entity_id=None):  # type: ignore[no-untyped-def]
        if organization_entity_id is None:
            return _msp_workspace(request, permission)
        return _organization_workspace(request, organization_entity_id, permission)

    @extend_schema(request=CredentialReferenceUpdateSerializer, responses={200: CredentialReferenceSerializer})
    def patch(self, request, credential_reference_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = self.workspace(request, PermissionKey.CREDENTIAL_REFERENCES_MANAGE, organization_entity_id)
        return _update(workspace, request, credential_reference_entity_id)

    @extend_schema(request=None, responses={204: OpenApiResponse(description="Credential reference archived")})
    def delete(self, request, credential_reference_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = self.workspace(request, PermissionKey.CREDENTIAL_REFERENCES_MANAGE, organization_entity_id)
        archive_credential_reference(
            reference=_get(workspace, credential_reference_entity_id), actor_id=request.user.pk
        )
        return Response(status=204)


class MSPCredentialReferenceDetailView(_CredentialReferenceDetailView):
    pass


class OrganizationCredentialReferenceDetailView(_CredentialReferenceDetailView):
    pass


class _CredentialReferenceOpenView(APIView):
    @extend_schema(responses={302: OpenApiResponse(description="Redirect to the validated external provider link")})
    def get(self, request, credential_reference_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        if organization_entity_id is None:
            workspace = _msp_workspace(request, PermissionKey.CREDENTIAL_REFERENCES_VIEW)
        else:
            workspace = _organization_workspace(
                request, organization_entity_id, PermissionKey.CREDENTIAL_REFERENCES_VIEW
            )
        require_permission(request.user, PermissionKey.CREDENTIAL_REFERENCES_OPEN, organization=workspace.organization)
        target = record_credential_reference_open(
            reference=_get(workspace, credential_reference_entity_id), actor_id=request.user.pk
        )
        return HttpResponseRedirect(target)


class MSPCredentialReferenceOpenView(_CredentialReferenceOpenView):
    pass


class OrganizationCredentialReferenceOpenView(_CredentialReferenceOpenView):
    pass
