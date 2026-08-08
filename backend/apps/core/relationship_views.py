from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import require_installation_member, require_installation_owner

from .relationship_serializers import (
    EntityLinkTypeSerializer,
    EntityLinkWriteSerializer,
    EntityRelationshipResultSerializer,
    EntityRelationshipSerializer,
    EntitySearchQuerySerializer,
    EntitySearchResultSerializer,
)
from .relationships import (
    EntityRelationshipError,
    archive_entity_link,
    create_entity_link,
    link_type_catalog,
    relationships_for_entity,
    search_entities,
)
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


def _workspace(request, organization_entity_id: UUID | None) -> ResolvedWorkspace:  # type: ignore[no-untyped-def]
    if organization_entity_id is None:
        return resolve_msp_workspace(request.user)
    return resolve_organization_workspace(request.user, entity_id=organization_entity_id)


def _not_found() -> NotFound:
    return NotFound("The record or relationship is not available in this workspace.")


class EntityLinkTypeCatalogView(APIView):
    @extend_schema(
        responses={
            200: EntityLinkTypeSerializer(many=True),
            403: OpenApiResponse(description="Installation membership required"),
        }
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        require_installation_member(request.user)
        return Response(EntityLinkTypeSerializer(link_type_catalog(), many=True).data)


class EntitySearchView(APIView):
    @extend_schema(
        operation_id="entities_search",
        parameters=[EntitySearchQuerySerializer],
        responses={
            200: EntitySearchResultSerializer,
            400: OpenApiResponse(description="Invalid search parameters"),
            403: OpenApiResponse(description="Workspace access required"),
            404: OpenApiResponse(description="Organization workspace not found"),
        },
    )
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        query = EntitySearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        results, count, has_more = search_entities(
            workspace=workspace,
            query=values["q"],
            entity_type=values["entity_type"],
            page=values["page"],
            page_size=values["page_size"],
        )
        response = {
            "results": results,
            "page": values["page"],
            "page_size": values["page_size"],
            "count": count,
            "has_more": has_more,
        }
        return Response(EntitySearchResultSerializer(response).data)


class EntityRelationshipListCreateView(APIView):
    @extend_schema(
        operation_id="entity_relationships_list",
        responses={
            200: EntityRelationshipResultSerializer,
            403: OpenApiResponse(description="Workspace access required"),
            404: OpenApiResponse(description="Entity not found in workspace"),
        },
    )
    def get(self, request, entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        try:
            relationships = relationships_for_entity(workspace=workspace, entity_id=entity_id)
        except ObjectDoesNotExist as exc:
            raise _not_found() from exc
        return Response(EntityRelationshipResultSerializer({"relationships": relationships}).data)

    @extend_schema(
        operation_id="entity_relationships_create",
        request=EntityLinkWriteSerializer,
        responses={
            201: EntityRelationshipSerializer,
            400: OpenApiResponse(description="Invalid or duplicate relationship"),
            403: OpenApiResponse(description="Installation owner with MFA required"),
            404: OpenApiResponse(description="Entity not found in workspace"),
        },
    )
    def post(self, request, entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        require_installation_owner(request.user)
        workspace = _workspace(request, organization_entity_id)
        serializer = EntityLinkWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            link = create_entity_link(
                workspace=workspace,
                source_entity_id=entity_id,
                target_entity_id=serializer.validated_data["target_id"],
                link_type=serializer.validated_data["link_type"],
                actor_id=request.user.pk,
            )
            relationship = next(
                item
                for item in relationships_for_entity(workspace=workspace, entity_id=entity_id)
                if item["id"] == link.id
            )
        except ObjectDoesNotExist as exc:
            raise _not_found() from exc
        except EntityRelationshipError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(EntityRelationshipSerializer(relationship).data, status=201)


class EntityRelationshipDetailView(APIView):
    @extend_schema(
        operation_id="entity_relationships_archive",
        request=None,
        responses={
            204: OpenApiResponse(description="Relationship archived"),
            403: OpenApiResponse(description="Installation owner with MFA required"),
            404: OpenApiResponse(description="Relationship not found in workspace"),
        },
    )
    def delete(self, request, entity_id, link_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        require_installation_owner(request.user)
        workspace = _workspace(request, organization_entity_id)
        try:
            archive_entity_link(
                workspace=workspace,
                entity_id=entity_id,
                link_id=link_id,
                actor_id=request.user.pk,
            )
        except ObjectDoesNotExist as exc:
            raise _not_found() from exc
        return Response(status=204)


@extend_schema_view(get=extend_schema(operation_id="msp_entities_search"))
class MSPEntitySearchView(EntitySearchView):
    pass


@extend_schema_view(get=extend_schema(operation_id="organization_entities_search"))
class OrganizationEntitySearchView(EntitySearchView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="msp_entity_relationships_list"),
    post=extend_schema(operation_id="msp_entity_relationships_create"),
)
class MSPEntityRelationshipListCreateView(EntityRelationshipListCreateView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_entity_relationships_list"),
    post=extend_schema(operation_id="organization_entity_relationships_create"),
)
class OrganizationEntityRelationshipListCreateView(EntityRelationshipListCreateView):
    pass


@extend_schema_view(delete=extend_schema(operation_id="msp_entity_relationships_archive"))
class MSPEntityRelationshipDetailView(EntityRelationshipDetailView):
    pass


@extend_schema_view(delete=extend_schema(operation_id="organization_entity_relationships_archive"))
class OrganizationEntityRelationshipDetailView(EntityRelationshipDetailView):
    pass
