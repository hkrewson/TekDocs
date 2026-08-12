
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .compliance_bundles import ComplianceBundleError, bundles_for_scope, create_bundle, verify_bundle
from .workspaces import resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        return super().to_internal_value(data)


class BundleWriteSerializer(StrictSerializer):
    title = serializers.CharField(max_length=240)
    reason = serializers.CharField(max_length=500)
    audience = serializers.ChoiceField(choices=("msp_internal", "client_auditor"))


class BundleSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    title = serializers.CharField(source="entity.display_name")
    reason = serializers.CharField()
    audience = serializers.CharField()
    manifest = serializers.JSONField()
    content_digest = serializers.CharField()
    signature = serializers.CharField()
    signature_algorithm = serializers.CharField()
    public_key = serializers.CharField()
    key_fingerprint = serializers.CharField()
    created_by = serializers.CharField(source="created_by.display_name")
    created_at = serializers.DateTimeField()
    verified = serializers.SerializerMethodField()

    def get_verified(self, value) -> bool:  # type: ignore[no-untyped-def]
        return verify_bundle(value)


class BundleListCreateView(APIView):
    @extend_schema(responses={200: BundleSerializer(many=True)})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = (
            resolve_organization_workspace(request.user, entity_id=organization_entity_id)
            if organization_entity_id
            else resolve_msp_workspace(request.user)
        )
        require_permission(request.user, PermissionKey.COMPLIANCE_VIEW, organization=workspace.organization)
        return Response(BundleSerializer(bundles_for_scope(workspace.data_scope)[:100], many=True).data)

    @extend_schema(request=BundleWriteSerializer, responses={201: BundleSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = (
            resolve_organization_workspace(request.user, entity_id=organization_entity_id)
            if organization_entity_id
            else resolve_msp_workspace(request.user)
        )
        require_permission(request.user, PermissionKey.COMPLIANCE_EDIT, organization=workspace.organization)
        serializer = BundleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            bundle = create_bundle(workspace=workspace, actor_id=request.user.pk, **serializer.validated_data)
        except ComplianceBundleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(BundleSerializer(bundle).data, status=201)


@extend_schema_view(
    get=extend_schema(operation_id="msp_compliance_bundle_list"),
    post=extend_schema(operation_id="msp_compliance_bundle_create"),
)
class MSPBundleListCreateView(BundleListCreateView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_compliance_bundle_list"),
    post=extend_schema(operation_id="organization_compliance_bundle_create"),
)
class OrganizationBundleListCreateView(BundleListCreateView):
    pass
