from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import require_installation_owner

from .models import Location, Site
from .scoping import DataScope
from .serializers import (
    LocationSerializer,
    LocationWriteSerializer,
    SiteQuerySerializer,
    SiteResultSerializer,
    SiteSerializer,
    SiteWriteSerializer,
)
from .sites import (
    SiteHierarchyError,
    archive_location,
    archive_site,
    create_location,
    create_site,
    locations_for_scope,
    query_sites,
    sites_for_scope,
    update_location,
    update_site,
)
from .workspaces import ResolvedWorkspace, resolve_organization_workspace


def _msp_workspace(request) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    member = require_installation_owner(request.user)
    return ResolvedWorkspace(
        member=member,
        kind="msp",
        id=member.tenant.id,
        name=member.tenant.name,
        data_scope=DataScope.tenant(member.tenant),
        classifications=(),
        capabilities=("sites",),
    )


def _organization_workspace(request, organization_entity_id: UUID) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    return resolve_organization_workspace(request.user, entity_id=organization_entity_id)


def _site(workspace: ResolvedWorkspace, site_entity_id: UUID) -> Site:
    return get_object_or_404(sites_for_scope(workspace.data_scope), entity_id=site_entity_id)


def _location(workspace: ResolvedWorkspace, site: Site, location_entity_id: UUID) -> Location:
    return get_object_or_404(
        locations_for_scope(workspace.data_scope),
        site=site,
        entity_id=location_entity_id,
    )


def _serialize_site(workspace: ResolvedWorkspace, site_entity_id: UUID) -> Response:
    return Response(SiteSerializer(_site(workspace, site_entity_id)).data)


def _list(workspace: ResolvedWorkspace, request) -> Response:  # type: ignore[no-untyped-def]
    serializer = SiteQuerySerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    records = query_sites(scope=workspace.data_scope, q=serializer.validated_data["q"])
    return Response(SiteResultSerializer({"results": records, "count": len(records)}).data)


def _create(workspace: ResolvedWorkspace, request) -> Response:  # type: ignore[no-untyped-def]
    serializer = SiteWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = {
        "code": "",
        "address_line_1": "",
        "address_line_2": "",
        "city": "",
        "region": "",
        "postal_code": "",
        "country_code": "",
        "timezone": "",
        "phone": "",
        **serializer.validated_data,
    }
    try:
        site = create_site(
            tenant=workspace.member.tenant,
            organization=workspace.organization,
            actor_id=request.user.pk,
            **values,
        )
    except IntegrityError as exc:
        raise serializers.ValidationError({"code": "Site codes must be unique within a workspace."}) from exc
    return Response(SiteSerializer(_site(workspace, site.entity_id)).data, status=201)


def _update(workspace: ResolvedWorkspace, site_entity_id: UUID, request) -> Response:  # type: ignore[no-untyped-def]
    site = _site(workspace, site_entity_id)
    serializer = SiteWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    values = {
        "name": site.entity.display_name,
        "code": site.code,
        "address_line_1": site.address_line_1,
        "address_line_2": site.address_line_2,
        "city": site.city,
        "region": site.region,
        "postal_code": site.postal_code,
        "country_code": site.country_code,
        "timezone": site.timezone,
        "phone": site.phone,
        **serializer.validated_data,
    }
    try:
        update_site(site=site, actor_id=request.user.pk, **values)
    except IntegrityError as exc:
        raise serializers.ValidationError({"code": "Site codes must be unique within a workspace."}) from exc
    return _serialize_site(workspace, site_entity_id)


def _archive(workspace: ResolvedWorkspace, site_entity_id: UUID, request) -> Response:  # type: ignore[no-untyped-def]
    archive_site(site=_site(workspace, site_entity_id), actor_id=request.user.pk)
    return Response(status=204)


def _create_location(workspace: ResolvedWorkspace, site_entity_id: UUID, request) -> Response:  # type: ignore[no-untyped-def]
    site = _site(workspace, site_entity_id)
    serializer = LocationWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = {"code": "", "parent_id": None, **serializer.validated_data}
    try:
        location = create_location(
            scope=workspace.data_scope,
            site=site,
            actor_id=request.user.pk,
            **values,
        )
    except SiteHierarchyError as exc:
        raise serializers.ValidationError({"parent_id": str(exc)}) from exc
    except IntegrityError as exc:
        raise serializers.ValidationError({"code": "Location codes must be unique beneath one parent."}) from exc
    return Response(LocationSerializer(_location(workspace, site, location.entity_id)).data, status=201)


def _update_location(
    workspace: ResolvedWorkspace,
    site_entity_id: UUID,
    location_entity_id: UUID,
    request: Request,
) -> Response:
    site = _site(workspace, site_entity_id)
    location = _location(workspace, site, location_entity_id)
    serializer = LocationWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    values = {
        "name": location.entity.display_name,
        "kind": location.kind,
        "code": location.code,
        "parent_id": location.parent.entity_id if location.parent is not None else None,
        **serializer.validated_data,
    }
    try:
        update_location(
            scope=workspace.data_scope,
            location=location,
            actor_id=request.user.pk,
            **values,
        )
    except SiteHierarchyError as exc:
        raise serializers.ValidationError({"parent_id": str(exc)}) from exc
    except IntegrityError as exc:
        raise serializers.ValidationError({"code": "Location codes must be unique beneath one parent."}) from exc
    return Response(LocationSerializer(_location(workspace, site, location_entity_id)).data)


def _archive_location(
    workspace: ResolvedWorkspace,
    site_entity_id: UUID,
    location_entity_id: UUID,
    request: Request,
) -> Response:
    site = _site(workspace, site_entity_id)
    archive_location(
        location=_location(workspace, site, location_entity_id),
        actor_id=request.user.pk,
    )
    return Response(status=204)


class MSPSiteListCreateView(APIView):
    @extend_schema(
        operation_id="sites_msp_list",
        parameters=[OpenApiParameter("q", str)],
        responses={200: SiteResultSerializer},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        return _list(_msp_workspace(request), request)

    @extend_schema(operation_id="sites_msp_create", request=SiteWriteSerializer, responses={201: SiteSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        return _create(_msp_workspace(request), request)


class MSPSiteDetailView(APIView):
    @extend_schema(operation_id="sites_msp_retrieve", responses={200: SiteSerializer, 404: OpenApiResponse()})
    def get(self, request, site_entity_id):  # type: ignore[no-untyped-def]
        return _serialize_site(_msp_workspace(request), site_entity_id)

    @extend_schema(operation_id="sites_msp_update", request=SiteWriteSerializer, responses={200: SiteSerializer})
    def patch(self, request, site_entity_id):  # type: ignore[no-untyped-def]
        return _update(_msp_workspace(request), site_entity_id, request)

    @extend_schema(operation_id="sites_msp_archive", request=None, responses={204: OpenApiResponse()})
    def delete(self, request, site_entity_id):  # type: ignore[no-untyped-def]
        return _archive(_msp_workspace(request), site_entity_id, request)


class MSPLocationListCreateView(APIView):
    @extend_schema(
        operation_id="locations_msp_create",
        request=LocationWriteSerializer,
        responses={201: LocationSerializer},
    )
    def post(self, request, site_entity_id):  # type: ignore[no-untyped-def]
        return _create_location(_msp_workspace(request), site_entity_id, request)


class MSPLocationDetailView(APIView):
    @extend_schema(
        operation_id="locations_msp_update",
        request=LocationWriteSerializer,
        responses={200: LocationSerializer},
    )
    def patch(self, request, site_entity_id, location_entity_id):  # type: ignore[no-untyped-def]
        return _update_location(_msp_workspace(request), site_entity_id, location_entity_id, request)

    @extend_schema(operation_id="locations_msp_archive", request=None, responses={204: OpenApiResponse()})
    def delete(self, request, site_entity_id, location_entity_id):  # type: ignore[no-untyped-def]
        return _archive_location(_msp_workspace(request), site_entity_id, location_entity_id, request)


class OrganizationSiteListCreateView(APIView):
    @extend_schema(
        operation_id="sites_organization_list",
        parameters=[OpenApiParameter("q", str)],
        responses={200: SiteResultSerializer},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _list(_organization_workspace(request, organization_entity_id), request)

    @extend_schema(
        operation_id="sites_organization_create",
        request=SiteWriteSerializer,
        responses={201: SiteSerializer},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _create(_organization_workspace(request, organization_entity_id), request)


class OrganizationSiteDetailView(APIView):
    @extend_schema(operation_id="sites_organization_retrieve", responses={200: SiteSerializer, 404: OpenApiResponse()})
    def get(self, request, organization_entity_id, site_entity_id):  # type: ignore[no-untyped-def]
        return _serialize_site(_organization_workspace(request, organization_entity_id), site_entity_id)

    @extend_schema(
        operation_id="sites_organization_update",
        request=SiteWriteSerializer,
        responses={200: SiteSerializer},
    )
    def patch(self, request, organization_entity_id, site_entity_id):  # type: ignore[no-untyped-def]
        return _update(_organization_workspace(request, organization_entity_id), site_entity_id, request)

    @extend_schema(operation_id="sites_organization_archive", request=None, responses={204: OpenApiResponse()})
    def delete(self, request, organization_entity_id, site_entity_id):  # type: ignore[no-untyped-def]
        return _archive(_organization_workspace(request, organization_entity_id), site_entity_id, request)


class OrganizationLocationListCreateView(APIView):
    @extend_schema(
        operation_id="locations_organization_create",
        request=LocationWriteSerializer,
        responses={201: LocationSerializer},
    )
    def post(self, request, organization_entity_id, site_entity_id):  # type: ignore[no-untyped-def]
        return _create_location(_organization_workspace(request, organization_entity_id), site_entity_id, request)


class OrganizationLocationDetailView(APIView):
    @extend_schema(
        operation_id="locations_organization_update",
        request=LocationWriteSerializer,
        responses={200: LocationSerializer},
    )
    def patch(self, request, organization_entity_id, site_entity_id, location_entity_id):  # type: ignore[no-untyped-def]
        return _update_location(
            _organization_workspace(request, organization_entity_id),
            site_entity_id,
            location_entity_id,
            request,
        )

    @extend_schema(operation_id="locations_organization_archive", request=None, responses={204: OpenApiResponse()})
    def delete(self, request, organization_entity_id, site_entity_id, location_entity_id):  # type: ignore[no-untyped-def]
        return _archive_location(
            _organization_workspace(request, organization_entity_id),
            site_entity_id,
            location_entity_id,
            request,
        )
