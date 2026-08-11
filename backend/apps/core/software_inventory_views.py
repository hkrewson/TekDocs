from __future__ import annotations

from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .collection_pagination import BoundedCollectionQuerySerializer, paginate
from .inventory import InventoryError, assets_for_scope, require_operational_owner
from .models import (
    ClientAsset,
    SoftwareInstallationStatus,
    SoftwareLicense,
    SoftwareLicenseKind,
    SoftwareLicenseStatus,
    SoftwareRenewalInterval,
)
from .software_inventory import (
    SoftwareInventoryError,
    assign_seat,
    create_license,
    installation_choices,
    licenses_for_scope,
    link_installation,
    revoke_seat,
    update_installation,
    update_license,
)
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class SoftwareInstallationWriteSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=SoftwareInstallationStatus.values, required=False)
    installed_version = serializers.CharField(max_length=160, allow_blank=True, required=False)
    installed_on = serializers.DateField(allow_null=True, required=False)
    last_verified_on = serializers.DateField(allow_null=True, required=False)
    site_id = serializers.UUIDField(allow_null=True, required=False)


class SoftwareInstallationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    asset_id = serializers.UUIDField(source="asset.entity_id")
    asset_name = serializers.CharField(source="asset.entity.display_name")
    product_id = serializers.UUIDField(source="asset.product.entity_id")
    product_name = serializers.CharField(source="asset.product.entity.display_name")
    model_name = serializers.CharField(source="asset.model.entity.display_name")
    status = serializers.CharField()
    installed_version = serializers.CharField()
    installed_on = serializers.DateField(allow_null=True)
    last_verified_on = serializers.DateField(allow_null=True)
    site_id = serializers.UUIDField(allow_null=True)
    site_name = serializers.CharField(source="site.entity.display_name", allow_null=True)


class LicenseWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, required=False)
    asset_id = serializers.UUIDField(required=False)
    kind = serializers.ChoiceField(choices=SoftwareLicenseKind.values, required=False)
    status = serializers.ChoiceField(choices=SoftwareLicenseStatus.values, required=False)
    seat_limit = serializers.IntegerField(min_value=1, max_value=100000, required=False)
    starts_on = serializers.DateField(allow_null=True, required=False)
    renews_on = serializers.DateField(allow_null=True, required=False)
    ends_on = serializers.DateField(allow_null=True, required=False)
    renewal_interval = serializers.ChoiceField(choices=SoftwareRenewalInterval.values, required=False)
    auto_renew = serializers.BooleanField(required=False)
    reference = serializers.CharField(max_length=240, allow_blank=True, required=False)


class SeatWriteSerializer(StrictSerializer):
    person_id = serializers.UUIDField(allow_null=True, required=False)
    installation_id = serializers.UUIDField(allow_null=True, required=False)


class InstallationLinkWriteSerializer(StrictSerializer):
    installation_id = serializers.UUIDField()


class SoftwareSeatSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    seat_number = serializers.IntegerField()
    person_id = serializers.UUIDField(allow_null=True)
    person_name = serializers.CharField(source="person.person.entity.display_name", allow_null=True)
    installation_id = serializers.UUIDField(allow_null=True)
    installation_name = serializers.CharField(source="installation.asset.entity.display_name", allow_null=True)
    assigned_at = serializers.DateTimeField()
    revoked_at = serializers.DateTimeField(allow_null=True)


class SoftwareLicenseEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    event_type = serializers.CharField()
    installation_name = serializers.CharField(source="installation.asset.entity.display_name", allow_null=True)
    person_name = serializers.CharField(source="person.person.entity.display_name", allow_null=True)
    seat_number = serializers.IntegerField(allow_null=True)
    occurred_at = serializers.DateTimeField()


class SoftwareLicenseSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    supplier_name = serializers.CharField(source="supplier.entity.display_name")
    product_id = serializers.UUIDField(source="product.entity_id")
    product_name = serializers.CharField(source="product.entity.display_name")
    model_name = serializers.CharField(source="model.entity.display_name", allow_null=True)
    kind = serializers.CharField()
    status = serializers.CharField()
    seat_limit = serializers.IntegerField()
    active_seats = serializers.SerializerMethodField()
    starts_on = serializers.DateField(allow_null=True)
    renews_on = serializers.DateField(allow_null=True)
    ends_on = serializers.DateField(allow_null=True)
    renewal_interval = serializers.CharField()
    auto_renew = serializers.BooleanField()
    reference = serializers.CharField()
    installations = serializers.SerializerMethodField()
    seats = SoftwareSeatSerializer(many=True)
    events = SoftwareLicenseEventSerializer(many=True)

    @extend_schema_field(serializers.IntegerField())
    def get_active_seats(self, item: SoftwareLicense) -> int:
        return sum(seat.revoked_at is None for seat in item.seats.all())

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_installations(self, item: SoftwareLicense) -> list[dict[str, object]]:
        return [
            {"id": str(link.installation_id), "name": link.installation.asset.entity.display_name}
            for link in item.installation_links.all()
            if link.archived_at is None
        ]


class LicenseResultSerializer(serializers.Serializer):
    results = SoftwareLicenseSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    can_manage = serializers.BooleanField()


class ChoiceResultSerializer(serializers.Serializer):
    installations = SoftwareInstallationSerializer(many=True)
    people = serializers.ListField()


def _workspace(request, organization_entity_id: UUID | None, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id is not None
        else resolve_msp_workspace(request.user)
    )
    require_permission(request.user, permission, organization=workspace.organization)
    try:
        require_operational_owner(workspace.organization)
    except InventoryError as exc:
        raise PermissionDenied(str(exc)) from exc
    return workspace


def _asset(workspace: ResolvedWorkspace, entity_id: UUID) -> ClientAsset:
    return get_object_or_404(assets_for_scope(workspace.data_scope), entity_id=entity_id)


def _license(workspace: ResolvedWorkspace, entity_id: UUID) -> SoftwareLicense:
    return get_object_or_404(licenses_for_scope(workspace.data_scope), entity_id=entity_id)


class ClientSoftwareInstallationDetailView(APIView):
    @extend_schema(request=SoftwareInstallationWriteSerializer, responses={200: SoftwareInstallationSerializer})
    def patch(self, request, organization_entity_id, asset_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = SoftwareInstallationWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            result = update_installation(
                asset=_asset(workspace, asset_entity_id),
                actor_id=request.user.pk,
                values=dict(serializer.validated_data),
            )
        except SoftwareInventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(SoftwareInstallationSerializer(result).data)


class SoftwareLicenseListCreateView(APIView):
    @extend_schema(parameters=[BoundedCollectionQuerySerializer], responses={200: LicenseResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        query = BoundedCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = paginate(licenses_for_scope(workspace.data_scope), **query.validated_data)
        return Response(
            LicenseResultSerializer(
                {
                    "results": page.records,
                    "page": page.page,
                    "page_size": page.page_size,
                    "count": page.count,
                    "has_more": page.has_more,
                    "can_manage": context_has_permission(
                        workspace.member, PermissionKey.ASSETS_EDIT, organization=workspace.organization
                    ),
                }
            ).data
        )

    @extend_schema(
        request=LicenseWriteSerializer,
        responses={201: SoftwareLicenseSerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = LicenseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if not {"name", "asset_id", "kind"}.issubset(values):
            raise serializers.ValidationError({"detail": "Name, software asset, and license kind are required."})
        asset = _asset(workspace, values.pop("asset_id"))
        values.setdefault("status", SoftwareLicenseStatus.ACTIVE)
        values.setdefault("seat_limit", 1)
        values.setdefault("renewal_interval", SoftwareRenewalInterval.NONE)
        values.setdefault("auto_renew", False)
        values.setdefault("reference", "")
        try:
            record = create_license(
                tenant=workspace.member.tenant,
                organization=workspace.organization,
                actor_id=request.user.pk,
                asset=asset,
                values=values,
            )
        except SoftwareInventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(SoftwareLicenseSerializer(record).data, status=201)


class SoftwareLicenseDetailView(APIView):
    @extend_schema(responses={200: SoftwareLicenseSerializer})
    def get(self, request, organization_entity_id, license_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        return Response(SoftwareLicenseSerializer(_license(workspace, license_entity_id)).data)

    @extend_schema(
        request=LicenseWriteSerializer,
        responses={200: SoftwareLicenseSerializer},
    )
    def patch(self, request, organization_entity_id, license_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = LicenseWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        forbidden = {"asset_id"}.intersection(serializer.validated_data)
        if forbidden:
            raise serializers.ValidationError({key: "This field cannot be changed." for key in forbidden})
        try:
            record = update_license(
                license_record=_license(workspace, license_entity_id),
                actor_id=request.user.pk,
                values=dict(serializer.validated_data),
            )
        except SoftwareInventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(SoftwareLicenseSerializer(record).data)


class SoftwareLicenseChoiceView(APIView):
    @extend_schema(responses={200: ChoiceResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        installations, people = installation_choices(workspace.data_scope)
        return Response(
            {
                "installations": SoftwareInstallationSerializer(installations, many=True).data,
                "people": [{"id": item.id, "name": item.person.entity.display_name} for item in people],
            }
        )


class SoftwareLicenseInstallationView(APIView):
    @extend_schema(request=InstallationLinkWriteSerializer, responses={200: SoftwareLicenseSerializer})
    def post(self, request, organization_entity_id, license_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = InstallationLinkWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = link_installation(
                license_record=_license(workspace, license_entity_id),
                installation_id=serializer.validated_data["installation_id"],
                actor_id=request.user.pk,
            )
        except SoftwareInventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(SoftwareLicenseSerializer(record).data)


class SoftwareLicenseSeatView(APIView):
    @extend_schema(request=SeatWriteSerializer, responses={200: SoftwareLicenseSerializer})
    def post(self, request, organization_entity_id, license_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = SeatWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = assign_seat(
                license_record=_license(workspace, license_entity_id),
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except SoftwareInventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(SoftwareLicenseSerializer(record).data)


class SoftwareLicenseSeatDetailView(APIView):
    @extend_schema(responses={200: SoftwareLicenseSerializer})
    def delete(self, request, organization_entity_id, license_entity_id, seat_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        try:
            record = revoke_seat(
                license_record=_license(workspace, license_entity_id),
                seat_id=seat_id,
                actor_id=request.user.pk,
            )
        except SoftwareInventoryError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(SoftwareLicenseSerializer(record).data)
