"""Explicitly paginated, lightweight asset browsing; legacy asset APIs stay intact."""

from django.db.models import F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission

from .collection_pagination import BoundedCollectionQuerySerializer, OffsetPageSerializer, paginate
from .inventory_views import _workspace
from .models import ClientAsset, HardwareLifecycleState, Site, SoftwareInstallationStatus

ORDER_FIELDS = {
    "name": "entity__display_name",
    "model": "model__entity__display_name",
    "kind": "product__kind",
    "status": "collection_status",
    "assignment": "hardware__assigned_person__person__entity__display_name",
    "site": "collection_site",
    "warranty": "hardware__warranty_ends_on",
}


class OptionalQueryBooleanField(serializers.BooleanField):
    # Query strings are not checkbox forms: omission must not mean False.
    default_empty_html = serializers.empty


class AssetCollectionQuerySerializer(BoundedCollectionQuerySerializer):
    page_size = serializers.ChoiceField(choices=(25, 50, 100), required=False, default=25)
    search = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    kind = serializers.ChoiceField(choices=("hardware", "software"), required=False)
    status = serializers.ChoiceField(
        choices=(*HardwareLifecycleState.values, *SoftwareInstallationStatus.values), required=False
    )
    site = serializers.UUIDField(required=False)
    assigned = OptionalQueryBooleanField(required=False)
    warranty = serializers.ChoiceField(choices=("expired", "current", "missing"), required=False)
    ordering = serializers.ChoiceField(
        choices=(*ORDER_FIELDS, *(f"-{field}" for field in ORDER_FIELDS)), required=False, default="name"
    )


class AssetCollectionItemSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    kind = serializers.CharField(source="product.kind")
    model_name = serializers.CharField(source="model.entity.display_name")
    model_number = serializers.CharField(source="model.model_number")
    status = serializers.CharField(source="collection_status", allow_null=True)
    assignment = serializers.CharField(source="hardware.assigned_person.person.entity.display_name", allow_null=True)
    site = serializers.CharField(source="collection_site", allow_null=True)
    warranty_ends_on = serializers.DateField(source="hardware.warranty_ends_on", allow_null=True)


class AssetCollectionResultSerializer(OffsetPageSerializer):
    results = AssetCollectionItemSerializer(many=True)
    can_manage = serializers.BooleanField()
    can_view_relationships = serializers.BooleanField()
    can_create_relationships = serializers.BooleanField()
    can_archive_relationships = serializers.BooleanField()


class AssetCollectionView(APIView):
    @extend_schema(parameters=[AssetCollectionQuerySerializer], responses={200: AssetCollectionResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        query = AssetCollectionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        # Do not reuse the detail queryset: it prefetches publications and history.
        records = (
            ClientAsset.scoped.for_scope(workspace.data_scope)
            .filter(archived_at__isnull=True, entity__archived_at__isnull=True)
            .select_related("entity", "product", "model__entity", "hardware__assigned_person__person__entity")
            .only(
                "entity__display_name",
                "product__kind",
                "model__entity__display_name",
                "model__model_number",
                "hardware__warranty_ends_on",
                "hardware__assigned_person__person__entity__display_name",
            )
            .annotate(
                collection_status=Coalesce("hardware__lifecycle_state", "software_installation__status"),
                collection_site=Coalesce(
                    "hardware__assigned_site__entity__display_name", "software_installation__site__entity__display_name"
                ),
            )
        )
        if values["search"]:
            search = values["search"]
            records = records.filter(
                Q(entity__display_name__icontains=search)
                | Q(model__entity__display_name__icontains=search)
                | Q(model__model_number__icontains=search)
                | Q(hardware__serial_number__icontains=search)
                | Q(hardware__asset_tag__icontains=search)
            )
        if "kind" in values:
            records = records.filter(product__kind=values["kind"])
        if "status" in values:
            records = records.filter(collection_status=values["status"])
        if "site" in values:
            records = records.filter(
                Q(hardware__assigned_site__entity_id=values["site"])
                | Q(software_installation__site__entity_id=values["site"])
            )
        if "assigned" in values:
            records = records.filter(hardware__assigned_person__isnull=not values["assigned"])
        if "warranty" in values:
            records = records.filter(product__kind="hardware")
            warranty = values["warranty"]
            if warranty == "missing":
                records = records.filter(hardware__warranty_ends_on__isnull=True)
            elif warranty == "expired":
                records = records.filter(hardware__warranty_ends_on__lt=timezone.localdate())
            else:
                records = records.filter(hardware__warranty_ends_on__gte=timezone.localdate())
        ordering = values["ordering"]
        field = F(ORDER_FIELDS[ordering.lstrip("-")])
        records = records.order_by(
            field.desc(nulls_last=True) if ordering.startswith("-") else field.asc(nulls_last=True), "entity_id"
        )
        page = paginate(records, page=values["page"], page_size=values["page_size"])
        permissions = {
            "can_manage": PermissionKey.ASSETS_EDIT,
            "can_view_relationships": PermissionKey.RELATIONSHIPS_VIEW,
            "can_create_relationships": PermissionKey.RELATIONSHIPS_CREATE,
            "can_archive_relationships": PermissionKey.RELATIONSHIPS_ARCHIVE,
        }
        return Response(
            AssetCollectionResultSerializer(
                {
                    "results": page.records,
                    "page": page.page,
                    "page_size": page.page_size,
                    "count": page.count,
                    "has_more": page.has_more,
                    **{
                        name: context_has_permission(workspace.member, permission, organization=workspace.organization)
                        for name, permission in permissions.items()
                    },
                }
            ).data
        )


class AssetSiteQuerySerializer(BoundedCollectionQuerySerializer):
    page_size = serializers.ChoiceField(choices=(25, 50, 100), required=False, default=25)
    search = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    selected = serializers.UUIDField(required=False)


class AssetSiteChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")


class AssetSiteResultSerializer(OffsetPageSerializer):
    results = AssetSiteChoiceSerializer(many=True)
    selected = AssetSiteChoiceSerializer(allow_null=True)


class AssetSiteChoicesView(APIView):
    """Only site identities already visible through assets in this exact workspace."""

    @extend_schema(parameters=[AssetSiteQuerySerializer], responses={200: AssetSiteResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        query = AssetSiteQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        assets = ClientAsset.scoped.for_scope(workspace.data_scope).filter(
            archived_at__isnull=True, entity__archived_at__isnull=True
        )
        sites = (
            Site.scoped.for_scope(workspace.data_scope)
            .filter(archived_at__isnull=True, entity__archived_at__isnull=True)
            .filter(
                Q(pk__in=assets.values("hardware__assigned_site_id"))
                | Q(pk__in=assets.values("software_installation__site_id"))
            )
            .select_related("entity")
            .only("entity__display_name")
            .order_by("entity__display_name", "entity_id")
        )
        selected = sites.filter(entity_id=values["selected"]).first() if "selected" in values else None
        page = paginate(
            sites.filter(entity__display_name__icontains=values["search"]),
            page=values["page"],
            page_size=values["page_size"],
        )
        return Response(
            AssetSiteResultSerializer(
                {
                    "results": page.records,
                    "page": page.page,
                    "page_size": page.page_size,
                    "count": page.count,
                    "has_more": page.has_more,
                    "selected": selected,
                }
            ).data
        )
