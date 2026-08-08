from __future__ import annotations

from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .models import PersonAssociation
from .people import archive_person_association, create_person, people_for_scope, query_people, update_person
from .scoping import DataScope
from .serializers import PeopleQuerySerializer, PeopleResultSerializer, PersonSerializer, PersonWriteSerializer
from .sites import locations_for_scope, sites_for_scope
from .workspaces import ResolvedWorkspace, resolve_organization_workspace


def _placement(workspace: ResolvedWorkspace, site_entity_id, location_entity_id):  # type: ignore[no-untyped-def]
    if site_entity_id is None:
        if location_entity_id is not None:
            raise serializers.ValidationError({"structured_location_id": "A location requires a selected site."})
        return None, None
    site = get_object_or_404(sites_for_scope(workspace.data_scope), entity_id=site_entity_id)
    if location_entity_id is None:
        return site, None
    location = get_object_or_404(
        locations_for_scope(workspace.data_scope),
        site=site,
        entity_id=location_entity_id,
    )
    return site, location


def _query_parameters() -> list[OpenApiParameter]:
    return [
        OpenApiParameter("q", str, description="Search every displayed person and association field."),
        OpenApiParameter("filter_field", str),
        OpenApiParameter("filter_value", str),
        OpenApiParameter("ordering", str),
        OpenApiParameter("page", int),
        OpenApiParameter("page_size", int),
    ]


def _msp_workspace(request, permission: PermissionKey) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    member = require_permission(request.user, permission)
    return ResolvedWorkspace(
        member=member,
        kind="msp",
        id=member.tenant.id,
        name=member.tenant.name,
        data_scope=DataScope.tenant(member.tenant),
        classifications=(),
        capabilities=("people",),
    )


def _organization_workspace(  # type: ignore[no-untyped-def]
    request, organization_entity_id: UUID, permission: PermissionKey
) -> ResolvedWorkspace:
    workspace = resolve_organization_workspace(request.user, entity_id=organization_entity_id)
    require_permission(request.user, permission, organization=workspace.organization)
    return workspace


def _list(workspace: ResolvedWorkspace, request) -> Response:  # type: ignore[no-untyped-def]
    query_serializer = PeopleQuerySerializer(data=request.query_params)
    query_serializer.is_valid(raise_exception=True)
    values = query_serializer.validated_data
    records, count, has_more = query_people(scope=workspace.data_scope, **values)
    return Response(
        PeopleResultSerializer(
            {
                "results": records,
                "page": values["page"],
                "page_size": values["page_size"],
                "count": count,
                "has_more": has_more,
            }
        ).data
    )


def _create(workspace: ResolvedWorkspace, request) -> Response:  # type: ignore[no-untyped-def]
    serializer = PersonWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = {
        "preferred_name": "",
        "role": "",
        "responsibility": "",
        "location": "",
        "office": "",
        "phone": "",
        "email": "",
        "site_id": None,
        "structured_location_id": None,
        **serializer.validated_data,
    }
    site, structured_location = _placement(
        workspace,
        values.pop("site_id"),
        values.pop("structured_location_id"),
    )
    association = create_person(
        tenant=workspace.member.tenant,
        organization=workspace.organization,
        actor_id=request.user.pk,
        site=site,
        structured_location=structured_location,
        **values,
    )
    association = people_for_scope(workspace.data_scope).get(pk=association.pk)
    return Response(PersonSerializer(association).data, status=201)


def _get_association(workspace: ResolvedWorkspace, person_entity_id: UUID) -> PersonAssociation:
    return get_object_or_404(people_for_scope(workspace.data_scope), person__entity_id=person_entity_id)


def _detail(workspace: ResolvedWorkspace, person_entity_id: UUID) -> Response:
    return Response(PersonSerializer(_get_association(workspace, person_entity_id)).data)


def _update(workspace: ResolvedWorkspace, person_entity_id: UUID, request) -> Response:  # type: ignore[no-untyped-def]
    association = _get_association(workspace, person_entity_id)
    serializer = PersonWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    current_site = association.site if association.site_id else None
    current_location = association.structured_location if association.structured_location_id else None
    values = {
        "full_name": association.person.entity.display_name,
        "preferred_name": association.person.preferred_name,
        "kind": association.kind,
        "role": association.role,
        "responsibility": association.responsibility,
        "location": association.location,
        "office": association.office,
        "site_id": current_site.entity_id if current_site is not None else None,
        "structured_location_id": current_location.entity_id if current_location is not None else None,
        "phone": association.person.phone,
        "email": association.person.email,
        **serializer.validated_data,
    }
    site, structured_location = _placement(
        workspace,
        values.pop("site_id"),
        values.pop("structured_location_id"),
    )
    update_person(
        association=association,
        actor_id=request.user.pk,
        site=site,
        structured_location=structured_location,
        **values,
    )
    return Response(PersonSerializer(_get_association(workspace, person_entity_id)).data)


def _archive(workspace: ResolvedWorkspace, person_entity_id: UUID, request) -> Response:  # type: ignore[no-untyped-def]
    archive_person_association(
        association=_get_association(workspace, person_entity_id),
        actor_id=request.user.pk,
    )
    return Response(status=204)


class MSPPeopleListCreateView(APIView):
    @extend_schema(
        operation_id="people_msp_list",
        parameters=_query_parameters(),
        responses={200: PeopleResultSerializer, 403: OpenApiResponse()},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        return _list(_msp_workspace(request, PermissionKey.PEOPLE_VIEW), request)

    @extend_schema(
        operation_id="people_msp_create",
        request=PersonWriteSerializer,
        responses={201: PersonSerializer, 403: OpenApiResponse()},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        return _create(_msp_workspace(request, PermissionKey.PEOPLE_CREATE), request)


class MSPPersonDetailView(APIView):
    @extend_schema(operation_id="people_msp_retrieve", responses={200: PersonSerializer, 404: OpenApiResponse()})
    def get(self, request, person_entity_id):  # type: ignore[no-untyped-def]
        return _detail(_msp_workspace(request, PermissionKey.PEOPLE_VIEW), person_entity_id)

    @extend_schema(
        operation_id="people_msp_update",
        request=PersonWriteSerializer,
        responses={200: PersonSerializer, 404: OpenApiResponse()},
    )
    def patch(self, request, person_entity_id):  # type: ignore[no-untyped-def]
        return _update(_msp_workspace(request, PermissionKey.PEOPLE_EDIT), person_entity_id, request)

    @extend_schema(
        operation_id="people_msp_archive",
        request=None,
        responses={204: OpenApiResponse(), 404: OpenApiResponse()},
    )
    def delete(self, request, person_entity_id):  # type: ignore[no-untyped-def]
        return _archive(_msp_workspace(request, PermissionKey.PEOPLE_ARCHIVE), person_entity_id, request)


class OrganizationPeopleListCreateView(APIView):
    @extend_schema(
        operation_id="people_organization_list",
        parameters=_query_parameters(),
        responses={200: PeopleResultSerializer, 404: OpenApiResponse()},
    )
    def get(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _list(_organization_workspace(request, organization_entity_id, PermissionKey.PEOPLE_VIEW), request)

    @extend_schema(
        operation_id="people_organization_create",
        request=PersonWriteSerializer,
        responses={201: PersonSerializer, 404: OpenApiResponse()},
    )
    def post(self, request, organization_entity_id):  # type: ignore[no-untyped-def]
        return _create(_organization_workspace(request, organization_entity_id, PermissionKey.PEOPLE_CREATE), request)


class OrganizationPersonDetailView(APIView):
    @extend_schema(
        operation_id="people_organization_retrieve",
        responses={200: PersonSerializer, 404: OpenApiResponse()},
    )
    def get(self, request, organization_entity_id, person_entity_id):  # type: ignore[no-untyped-def]
        return _detail(
            _organization_workspace(request, organization_entity_id, PermissionKey.PEOPLE_VIEW), person_entity_id
        )

    @extend_schema(
        operation_id="people_organization_update",
        request=PersonWriteSerializer,
        responses={200: PersonSerializer, 404: OpenApiResponse()},
    )
    def patch(self, request, organization_entity_id, person_entity_id):  # type: ignore[no-untyped-def]
        return _update(
            _organization_workspace(request, organization_entity_id, PermissionKey.PEOPLE_EDIT),
            person_entity_id,
            request,
        )

    @extend_schema(
        operation_id="people_organization_archive",
        request=None,
        responses={204: OpenApiResponse(), 404: OpenApiResponse()},
    )
    def delete(self, request, organization_entity_id, person_entity_id):  # type: ignore[no-untyped-def]
        return _archive(
            _organization_workspace(request, organization_entity_id, PermissionKey.PEOPLE_ARCHIVE),
            person_entity_id,
            request,
        )
