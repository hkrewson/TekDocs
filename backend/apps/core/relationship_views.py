import csv
import io
import json
import math
from html import escape
from typing import Any, cast
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .models import RelationshipGraphSnapshot, workspace_for_owner
from .models import RelationshipGraphView as RelationshipGraphViewModel
from .relationship_serializers import (
    EntityLinkTypeSerializer,
    EntityLinkWriteSerializer,
    EntityRelationshipResultSerializer,
    EntityRelationshipSerializer,
    EntitySearchQuerySerializer,
    EntitySearchResultSerializer,
    RelationshipGraphQuerySerializer,
    RelationshipGraphSerializer,
    RelationshipGraphSnapshotSerializer,
    RelationshipGraphViewSerializer,
    RelationshipGraphViewWriteSerializer,
)
from .relationships import (
    EntityRelationshipError,
    archive_entity_link,
    create_entity_link,
    create_graph_snapshot,
    graph_snapshot_is_visible,
    graph_view_projection,
    link_type_catalog,
    relationship_graph_projection,
    relationships_for_entity,
    save_graph_view,
    search_entities,
)
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


def _workspace(  # type: ignore[no-untyped-def]
    request, organization_entity_id: UUID | None, permission: PermissionKey
) -> ResolvedWorkspace:
    if organization_entity_id is None:
        workspace = resolve_msp_workspace(request.user)
    else:
        workspace = resolve_organization_workspace(request.user, entity_id=organization_entity_id)
    require_permission(request.user, permission, organization=workspace.organization)
    return workspace


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
        require_permission(request.user, PermissionKey.RELATIONSHIPS_VIEW)
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
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_VIEW)
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
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_VIEW)
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
            403: OpenApiResponse(description="Relationship creation permission and MFA required"),
            404: OpenApiResponse(description="Entity not found in workspace"),
        },
    )
    def post(self, request, entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_CREATE)
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
            403: OpenApiResponse(description="Relationship archive permission and MFA required"),
            404: OpenApiResponse(description="Relationship not found in workspace"),
        },
    )
    def delete(self, request, entity_id, link_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_ARCHIVE)
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


class RelationshipGraphView(APIView):
    @extend_schema(
        operation_id="relationship_graph",
        parameters=[RelationshipGraphQuerySerializer],
        responses={
            200: RelationshipGraphSerializer,
            400: OpenApiResponse(description="Invalid graph parameters"),
            403: OpenApiResponse(description="Workspace or record permission required"),
            404: OpenApiResponse(description="Root entity not found in workspace"),
        },
    )
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_VIEW)
        serializer = RelationshipGraphQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            graph = relationship_graph_projection(workspace=workspace, **serializer.validated_data)
        except ObjectDoesNotExist as exc:
            raise _not_found() from exc
        return Response(RelationshipGraphSerializer(graph).data)


def _saved_views(workspace: ResolvedWorkspace):  # type: ignore[no-untyped-def]
    owner = workspace_for_owner(tenant=workspace.member.tenant, organization=workspace.organization)
    return RelationshipGraphViewModel.scoped.for_tenant(workspace.member.tenant).filter(
        workspace=owner, archived_at__isnull=True
    )


def _saved_view(workspace: ResolvedWorkspace, view_id: UUID) -> RelationshipGraphViewModel:
    try:
        return cast(RelationshipGraphViewModel, _saved_views(workspace).get(id=view_id))
    except ObjectDoesNotExist as exc:
        raise _not_found() from exc


class RelationshipGraphSavedViewListCreateView(APIView):
    serializer_class = RelationshipGraphViewWriteSerializer

    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_VIEW)
        records = []
        for view in _saved_views(workspace):
            try:
                records.append(graph_view_projection(workspace=workspace, view=view))
            except ObjectDoesNotExist:
                continue
        return Response(RelationshipGraphViewSerializer(records, many=True).data)

    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_CREATE)
        serializer = RelationshipGraphViewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            view = save_graph_view(workspace=workspace, actor_id=request.user.pk, values=serializer.validated_data)
        except ObjectDoesNotExist as exc:
            raise _not_found() from exc
        except IntegrityError as exc:
            raise ValidationError({"name": "A saved relationship graph with this name already exists."}) from exc
        data = RelationshipGraphViewSerializer(graph_view_projection(workspace=workspace, view=view)).data
        return Response(data, status=201)


class RelationshipGraphSavedViewDetailView(APIView):
    serializer_class = RelationshipGraphViewWriteSerializer

    def patch(self, request, view_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_CREATE)
        view = _saved_view(workspace, view_id)
        current = {
            "name": view.name,
            "family": view.family,
            "root_entity_id": view.root_entity_id,
            "depth": view.depth,
            "edge_limit": view.edge_limit,
            "positions": view.positions,
        }
        serializer = RelationshipGraphViewWriteSerializer(data={**current, **request.data})
        serializer.is_valid(raise_exception=True)
        try:
            view = save_graph_view(
                workspace=workspace,
                actor_id=request.user.pk,
                values=serializer.validated_data,
                view=view,
            )
        except (ObjectDoesNotExist, IntegrityError) as exc:
            if isinstance(exc, ObjectDoesNotExist):
                raise _not_found() from exc
            raise ValidationError({"name": "A saved relationship graph with this name already exists."}) from exc
        data = RelationshipGraphViewSerializer(graph_view_projection(workspace=workspace, view=view)).data
        return Response(data)

    def delete(self, request, view_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_ARCHIVE)
        view = _saved_view(workspace, view_id)
        view.archived_at = timezone.now()
        view.save(update_fields=("archived_at", "updated_at"))
        return Response(status=204)


def _snapshot_response(snapshot: RelationshipGraphSnapshot) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "view_id": snapshot.view_id,
        "content_digest": snapshot.content_digest,
        "graph": snapshot.graph,
        "created_at": snapshot.created_at,
    }


class RelationshipGraphSnapshotListCreateView(APIView):
    serializer_class = RelationshipGraphSnapshotSerializer

    def get(self, request, view_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_VIEW)
        view = _saved_view(workspace, view_id)
        snapshots = RelationshipGraphSnapshot.scoped.for_tenant(workspace.member.tenant).filter(view=view)[:100]
        visible = [
            _snapshot_response(item)
            for item in snapshots
            if graph_snapshot_is_visible(workspace=workspace, graph=item.graph)
        ]
        return Response(RelationshipGraphSnapshotSerializer(visible, many=True).data)

    def post(self, request, view_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_CREATE)
        view = _saved_view(workspace, view_id)
        snapshot = create_graph_snapshot(workspace=workspace, actor_id=request.user.pk, view=view)
        return Response(RelationshipGraphSnapshotSerializer(_snapshot_response(snapshot)).data, status=201)


def _snapshot_svg(graph: dict[str, Any]) -> str:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    positions = graph.get("positions", {})
    calculated = {}
    count = max(len(nodes), 1)
    for index, node in enumerate(nodes):
        node_id = node["id"]
        saved = positions.get(node_id) if isinstance(positions, dict) else None
        calculated[node_id] = (
            saved
            if isinstance(saved, dict)
            else {
                "x": 400 + 260 * math.cos(index * 2 * math.pi / count),
                "y": 300 + 220 * math.sin(index * 2 * math.pi / count),
            }
        )
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600">',
        '<rect width="800" height="600" fill="white"/>',
    ]
    for edge in edges:
        source, target = calculated.get(edge["source"]), calculated.get(edge["target"])
        if source and target:
            parts.append(
                f'<line x1="{source["x"]}" y1="{source["y"]}" '
                f'x2="{target["x"]}" y2="{target["y"]}" stroke="#888"/>'
            )
    for node in nodes:
        point = calculated[node["id"]]
        parts.append(
            f'<circle cx="{point["x"]}" cy="{point["y"]}" r="18" fill="#3f6f75"/>'
            f'<text x="{point["x"]}" y="{point["y"] + 34}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="11">{escape(node["label"])}</text>'
        )
    return "".join((*parts, "</svg>"))


class RelationshipGraphSnapshotExportView(APIView):
    serializer_class = RelationshipGraphSnapshotSerializer

    def get(self, request, snapshot_id, export_format, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id, PermissionKey.RELATIONSHIPS_VIEW)
        owner = workspace_for_owner(tenant=workspace.member.tenant, organization=workspace.organization)
        try:
            snapshot = RelationshipGraphSnapshot.scoped.for_tenant(workspace.member.tenant).get(
                id=snapshot_id, workspace=owner
            )
        except ObjectDoesNotExist as exc:
            raise _not_found() from exc
        if not graph_snapshot_is_visible(workspace=workspace, graph=snapshot.graph):
            raise _not_found()
        if export_format == "json":
            content = json.dumps(_snapshot_response(snapshot), sort_keys=True, separators=(",", ":"))
            media_type, suffix = "application/json", "json"
        elif export_format == "csv":
            stream = io.StringIO()
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(("source", "relationship", "target"))
            labels = {item["id"]: item["label"] for item in snapshot.graph["nodes"]}
            for edge in snapshot.graph["edges"]:
                writer.writerow((labels[edge["source"]], edge["label"], labels[edge["target"]]))
            content, media_type, suffix = stream.getvalue(), "text/csv", "csv"
        elif export_format == "svg":
            content, media_type, suffix = _snapshot_svg(snapshot.graph), "image/svg+xml", "svg"
        else:
            raise NotFound("That relationship graph export format is not available.")
        response = HttpResponse(content, content_type=media_type)
        response["Content-Disposition"] = f'attachment; filename="relationship-graph-{snapshot.id}.{suffix}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


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


@extend_schema_view(get=extend_schema(operation_id="msp_relationship_graph"))
class MSPRelationshipGraphView(RelationshipGraphView):
    pass


@extend_schema_view(get=extend_schema(operation_id="organization_relationship_graph"))
class OrganizationRelationshipGraphView(RelationshipGraphView):
    pass
