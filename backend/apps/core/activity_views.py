from typing import Any

from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .models import AuditEvent, Entity
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class ActivityQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    actor_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    occurred_after = serializers.DateTimeField(required=False, allow_null=True, default=None)
    occurred_before = serializers.DateTimeField(required=False, allow_null=True, default=None)
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=50)


class ActivityRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    action = serializers.CharField()
    actor_id = serializers.UUIDField(allow_null=True)
    actor_name = serializers.CharField(allow_null=True)
    entity_id = serializers.UUIDField(allow_null=True)
    entity_name = serializers.CharField(allow_null=True)
    entity_type = serializers.CharField(allow_null=True)
    request_id = serializers.UUIDField(allow_null=True)
    occurred_at = serializers.DateTimeField()


class ActivityResultSerializer(serializers.Serializer):
    results = ActivityRecordSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()
    actions = serializers.ListField(child=serializers.CharField())


def _workspace(request: Any, organization_entity_id: Any = None) -> ResolvedWorkspace:
    workspace = (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id
        else resolve_msp_workspace(request.user)
    )
    require_permission(request.user, PermissionKey.ACTIVITY_VIEW, organization=workspace.organization)
    return workspace


def _activity(workspace: ResolvedWorkspace, request: Any) -> Response:
    serializer = ActivityQuerySerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    entities = Entity.scoped.for_scope(workspace.data_scope)
    entity_ids = entities.values_list("id", flat=True)
    events = AuditEvent.scoped.for_tenant(workspace.member.tenant).select_related("actor")
    if workspace.organization is None:
        events = events.filter(Q(entity_id__in=entity_ids) | Q(entity_id__isnull=True))
    else:
        events = events.filter(
            Q(entity_id__in=entity_ids) | Q(entity_id=workspace.organization.entity_id)
        )
    if values["q"]:
        events = events.filter(action__icontains=values["q"])
    if values["actor_id"]:
        events = events.filter(actor_id=values["actor_id"])
    if values["occurred_after"]:
        events = events.filter(occurred_at__gte=values["occurred_after"])
    if values["occurred_before"]:
        events = events.filter(occurred_at__lte=values["occurred_before"])
    count = events.count()
    actions = list(events.order_by("action").values_list("action", flat=True).distinct()[:200])
    offset = (values["page"] - 1) * values["page_size"]
    selected = list(events.order_by("-occurred_at", "-id")[offset : offset + values["page_size"] + 1])
    entity_map = {
        str(entity.id): entity
        for entity in Entity.scoped.for_tenant(workspace.member.tenant).filter(
            id__in=[event.entity_id for event in selected if event.entity_id]
        )
    }
    records = []
    for event in selected[: values["page_size"]]:
        entity = entity_map.get(str(event.entity_id)) if event.entity_id else None
        records.append(
            {
                "id": event.id,
                "action": event.action,
                "actor_id": event.actor_id,
                "actor_name": event.actor.display_name if event.actor else None,
                "entity_id": event.entity_id,
                "entity_name": entity.display_name if entity else None,
                "entity_type": entity.entity_type if entity else None,
                "request_id": event.request_id,
                "occurred_at": event.occurred_at,
            }
        )
    payload = {
        "results": records,
        "count": count,
        "page": values["page"],
        "page_size": values["page_size"],
        "has_more": len(selected) > values["page_size"],
        "actions": actions,
    }
    return Response(ActivityResultSerializer(payload).data)


class ActivityListView(APIView):
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        return _activity(_workspace(request, organization_entity_id), request)


@extend_schema_view(get=extend_schema(operation_id="activity_msp_list", responses={200: ActivityResultSerializer}))
class MSPActivityListView(ActivityListView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="activity_organization_list", responses={200: ActivityResultSerializer})
)
class OrganizationActivityListView(ActivityListView):
    pass
