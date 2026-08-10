from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, context_has_permission, require_permission

from .catalogs import (
    CatalogError,
    StaleCatalogRevision,
    archive_model,
    archive_product,
    create_definition,
    create_definition_version,
    create_model,
    create_product,
    definitions_for_scope,
    products_for_scope,
    require_supplier,
    revise_model,
    update_product,
)
from .models import (
    CatalogModel,
    CatalogModelLifecycle,
    CatalogModelRevision,
    CatalogProduct,
    CatalogProductKind,
    CatalogSpecificationDefinition,
    CatalogSpecificationDefinitionVersion,
    Organization,
)
from .workspaces import ResolvedWorkspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: "This field is not accepted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class ProductWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    kind = serializers.ChoiceField(choices=CatalogProductKind.choices)
    description = serializers.CharField(max_length=1000, allow_blank=True, required=False, default="")


class ProductUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    description = serializers.CharField(max_length=1000, allow_blank=True, required=False, default="")


class DefinitionWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=160, trim_whitespace=True)
    product_kind = serializers.ChoiceField(choices=CatalogProductKind.choices)
    schema = serializers.JSONField()


class DefinitionVersionWriteSerializer(StrictSerializer):
    schema = serializers.JSONField()


class ModelWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=240, trim_whitespace=True)
    model_number = serializers.CharField(max_length=160, trim_whitespace=True)
    specification_version_id = serializers.UUIDField()
    lifecycle = serializers.ChoiceField(choices=CatalogModelLifecycle.choices)
    specifications = serializers.JSONField()
    notes = serializers.CharField(max_length=1000, allow_blank=True, required=False, default="")


class ModelRevisionWriteSerializer(ModelWriteSerializer):
    base_revision_id = serializers.UUIDField()


class CatalogModelRevisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    parent_id = serializers.UUIDField(allow_null=True)
    specification_version_id = serializers.UUIDField()
    specification_definition_id = serializers.SerializerMethodField()
    specification_definition_name = serializers.SerializerMethodField()
    specification_version = serializers.SerializerMethodField()
    lifecycle = serializers.ChoiceField(choices=CatalogModelLifecycle.choices)
    specifications = serializers.JSONField()
    notes = serializers.CharField()
    checksum = serializers.CharField()
    created_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    @extend_schema_field(serializers.UUIDField())
    def get_specification_definition_id(self, item):  # type: ignore[no-untyped-def]
        return item.specification_version.definition_id

    @extend_schema_field(serializers.CharField())
    def get_specification_definition_name(self, item):  # type: ignore[no-untyped-def]
        return item.specification_version.definition.name

    @extend_schema_field(serializers.IntegerField())
    def get_specification_version(self, item):  # type: ignore[no-untyped-def]
        return item.specification_version.version

    @extend_schema_field(serializers.CharField())
    def get_created_by(self, item):  # type: ignore[no-untyped-def]
        return item.created_by.display_name if item.created_by else "Unavailable user"


class CatalogModelSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    model_number = serializers.CharField()
    current_revision = serializers.SerializerMethodField()
    revisions = serializers.SerializerMethodField()

    @extend_schema_field(CatalogModelRevisionSerializer(allow_null=True))
    def get_current_revision(self, item):  # type: ignore[no-untyped-def]
        revisions = list(item.revisions.all())
        return CatalogModelRevisionSerializer(revisions[-1]).data if revisions else None

    @extend_schema_field(CatalogModelRevisionSerializer(many=True))
    def get_revisions(self, item):  # type: ignore[no-untyped-def]
        return CatalogModelRevisionSerializer(item.revisions.all(), many=True).data


class CatalogProductSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="entity.display_name")
    kind = serializers.ChoiceField(choices=CatalogProductKind.choices)
    description = serializers.CharField()
    updated_at = serializers.DateTimeField()
    models = CatalogModelSerializer(many=True)


class CatalogProductResultSerializer(serializers.Serializer):
    results = CatalogProductSerializer(many=True)
    can_manage = serializers.BooleanField()


class SpecificationVersionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    schema = serializers.JSONField()
    checksum = serializers.CharField()
    created_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    @extend_schema_field(serializers.CharField())
    def get_created_by(self, item):  # type: ignore[no-untyped-def]
        return item.created_by.display_name if item.created_by else "Unavailable user"


class SpecificationDefinitionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    product_kind = serializers.ChoiceField(choices=CatalogProductKind.choices)
    versions = SpecificationVersionSerializer(many=True)


class SpecificationDefinitionResultSerializer(serializers.Serializer):
    results = SpecificationDefinitionSerializer(many=True)
    can_manage = serializers.BooleanField()


def _workspace(request, organization_entity_id: UUID, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    workspace = resolve_organization_workspace(request.user, entity_id=organization_entity_id)
    require_permission(request.user, permission, organization=workspace.organization)
    if workspace.organization is None:
        raise PermissionDenied("A supplier organization workspace is required.")
    try:
        require_supplier(workspace.organization)
    except CatalogError as exc:
        raise PermissionDenied(str(exc)) from exc
    return workspace


def _can_manage(workspace: ResolvedWorkspace) -> bool:
    return context_has_permission(workspace.member, PermissionKey.ASSETS_EDIT, organization=workspace.organization)


def _supplier_organization(workspace: ResolvedWorkspace) -> Organization:
    if workspace.organization is None:
        raise PermissionDenied("A supplier organization workspace is required.")
    return workspace.organization


def _products(workspace: ResolvedWorkspace, request) -> Response:  # type: ignore[no-untyped-def]
    query = str(request.query_params.get("q", "")).strip()[:240]
    kind = str(request.query_params.get("kind", "")).strip()
    if kind and kind not in CatalogProductKind.values:
        raise serializers.ValidationError({"kind": "Choose hardware or software."})
    return Response(
        CatalogProductResultSerializer(
            {
                "results": products_for_scope(workspace.data_scope, query=query, kind=kind),
                "can_manage": _can_manage(workspace),
            }
        ).data
    )


def _product(workspace: ResolvedWorkspace, product_entity_id: UUID) -> CatalogProduct:
    return get_object_or_404(products_for_scope(workspace.data_scope), entity_id=product_entity_id)


def _model(workspace: ResolvedWorkspace, product: CatalogProduct, model_entity_id: UUID) -> CatalogModel:
    return get_object_or_404(
        CatalogModel.scoped.for_scope(workspace.data_scope)
        .filter(archived_at__isnull=True, entity__archived_at__isnull=True, product=product)
        .select_related("entity", "product"),
        entity_id=model_entity_id,
    )


def _definition(workspace: ResolvedWorkspace, definition_id: UUID) -> CatalogSpecificationDefinition:
    return get_object_or_404(definitions_for_scope(workspace.data_scope), id=definition_id)


def _definition_version(workspace: ResolvedWorkspace, version_id: UUID) -> CatalogSpecificationDefinitionVersion:
    return get_object_or_404(
        CatalogSpecificationDefinitionVersion.scoped.for_scope(workspace.data_scope).select_related("definition"),
        id=version_id,
    )


class CatalogProductListCreateView(APIView):
    @extend_schema(
        operation_id="organization_catalog_products_list",
        parameters=[OpenApiParameter("q", str), OpenApiParameter("kind", str)],
        responses={200: CatalogProductResultSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _products(_workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW), request)

    @extend_schema(request=ProductWriteSerializer, responses={201: CatalogProductSerializer})
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = ProductWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            product = create_product(
                tenant=workspace.member.tenant,
                organization=_supplier_organization(workspace),
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (CatalogError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(CatalogProductSerializer(product).data, status=201)


class CatalogProductDetailView(APIView):
    @extend_schema(operation_id="organization_catalog_products_retrieve", responses={200: CatalogProductSerializer})
    def get(self, request, organization_entity_id, product_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        return Response(CatalogProductSerializer(_product(workspace, product_entity_id)).data)

    @extend_schema(request=ProductUpdateSerializer, responses={200: CatalogProductSerializer})
    def patch(self, request, organization_entity_id, product_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = ProductUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = update_product(
            product=_product(workspace, product_entity_id), actor_id=request.user.pk, **serializer.validated_data
        )
        return Response(CatalogProductSerializer(product).data)

    @extend_schema(request=None, responses={204: OpenApiResponse(description="Product archived")})
    def delete(self, request, organization_entity_id, product_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        archive_product(product=_product(workspace, product_entity_id), actor_id=request.user.pk)
        return Response(status=204)


class CatalogModelListCreateView(APIView):
    @extend_schema(request=ModelWriteSerializer, responses={201: CatalogModelSerializer})
    def post(self, request, organization_entity_id, product_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = ModelWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        version = _definition_version(workspace, data.pop("specification_version_id"))
        try:
            model = create_model(
                product=_product(workspace, product_entity_id),
                actor_id=request.user.pk,
                specification_version=version,
                **data,
            )
        except (CatalogError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        model = _model(workspace, _product(workspace, product_entity_id), model.entity_id)
        model = (
            CatalogModel.scoped.for_scope(workspace.data_scope)
            .prefetch_related(
                Prefetch(
                    "revisions",
                    queryset=CatalogModelRevision.objects.select_related(
                        "specification_version", "specification_version__definition", "created_by"
                    ),
                )
            )
            .get(pk=model.pk)
        )
        return Response(CatalogModelSerializer(model).data, status=201)


class CatalogModelDetailView(APIView):
    @extend_schema(
        request=ModelRevisionWriteSerializer, responses={200: CatalogModelSerializer, 409: OpenApiResponse()}
    )
    def patch(self, request, organization_entity_id, product_entity_id, model_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        product = _product(workspace, product_entity_id)
        model = _model(workspace, product, model_entity_id)
        serializer = ModelRevisionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        version = _definition_version(workspace, data.pop("specification_version_id"))
        try:
            revise_model(model=model, actor_id=request.user.pk, specification_version=version, **data)
        except StaleCatalogRevision as exc:
            return Response(
                {"detail": str(exc), "current_revision": CatalogModelRevisionSerializer(exc.current_revision).data},
                status=409,
            )
        except (CatalogError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        refreshed = products_for_scope(workspace.data_scope).get(pk=product.pk).models.get(pk=model.pk)
        return Response(CatalogModelSerializer(refreshed).data)

    @extend_schema(request=None, responses={204: OpenApiResponse(description="Model archived")})
    def delete(self, request, organization_entity_id, product_entity_id, model_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        product = _product(workspace, product_entity_id)
        archive_model(model=_model(workspace, product, model_entity_id), actor_id=request.user.pk)
        return Response(status=204)


class CatalogSpecificationDefinitionListCreateView(APIView):
    @extend_schema(responses={200: SpecificationDefinitionResultSerializer})
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_VIEW)
        return Response(
            SpecificationDefinitionResultSerializer(
                {"results": definitions_for_scope(workspace.data_scope), "can_manage": _can_manage(workspace)}
            ).data
        )

    @extend_schema(request=DefinitionWriteSerializer, responses={201: SpecificationDefinitionSerializer})
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = DefinitionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            definition = create_definition(
                tenant=workspace.member.tenant,
                organization=_supplier_organization(workspace),
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (CatalogError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        definition = definitions_for_scope(workspace.data_scope).get(pk=definition.pk)
        return Response(SpecificationDefinitionSerializer(definition).data, status=201)


class CatalogSpecificationDefinitionVersionView(APIView):
    @extend_schema(request=DefinitionVersionWriteSerializer, responses={201: SpecificationVersionSerializer})
    def post(self, request, organization_entity_id, definition_id):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.ASSETS_EDIT)
        serializer = DefinitionVersionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            version = create_definition_version(
                definition=_definition(workspace, definition_id),
                actor_id=request.user.pk,
                **serializer.validated_data,
            )
        except (CatalogError, IntegrityError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(SpecificationVersionSerializer(version).data, status=201)
