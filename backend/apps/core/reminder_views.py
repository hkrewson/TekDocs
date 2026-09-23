from typing import Any

from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .reminders import ReminderError, ReminderInput, calendar_bytes, create_reminder, reminders_for_scope
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        return super().to_internal_value(data)


class ReminderWriteSerializer(StrictSerializer):
    source_entity_id = serializers.UUIDField()
    domain = serializers.ChoiceField(choices=("compliance", "inventory", "domain", "documentation"))
    kind = serializers.RegexField(r"^[a-z0-9_]{1,48}$")
    title = serializers.CharField(max_length=240)
    due_on = serializers.DateField()
    lead_days = serializers.IntegerField(min_value=0, max_value=3650, default=30)
    recurrence = serializers.ChoiceField(choices=("none", "annual"), default="none")
    owner_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class ReminderSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    source_entity_id = serializers.UUIDField()
    source = serializers.CharField(source="source_entity.display_name")
    domain = serializers.CharField()
    kind = serializers.CharField()
    title = serializers.CharField()
    due_on = serializers.DateField()
    lead_days = serializers.IntegerField()
    recurrence = serializers.CharField()
    owner_id = serializers.UUIDField(allow_null=True)
    owner = serializers.CharField(source="owner.display_name", allow_null=True)
    active = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class ReminderQuerySerializer(serializers.Serializer):
    paginated = serializers.BooleanField(default=False)
    q = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    domain = serializers.ChoiceField(
        choices=("compliance", "inventory", "domain", "documentation", "invoice"),
        required=False,
        allow_blank=True,
        default="",
    )
    ordering = serializers.ChoiceField(
        choices=("due_on", "-due_on", "title", "-title"),
        default="due_on",
    )
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.ChoiceField(choices=(25, 50, 100), default=25)


class ReminderResultSerializer(serializers.Serializer):
    results = ReminderSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_more = serializers.BooleanField()


def _workspace(request: Any, organization_entity_id: Any = None) -> ResolvedWorkspace:
    return (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id
        else resolve_msp_workspace(request.user)
    )


class ReminderListCreateView(APIView):
    @extend_schema(
        parameters=[ReminderQuerySerializer],
        responses={
            200: PolymorphicProxySerializer(
                component_name="ReminderCollectionResponse",
                serializers=[ReminderSerializer(many=True), ReminderResultSerializer],
                resource_type_field_name=None,
                many=False,
            )
        },
        description="Returns the legacy reminder array unless paginated=true requests the bounded collection shape.",
    )
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DEADLINES_VIEW, organization=workspace.organization)
        query = ReminderQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        records = reminders_for_scope(workspace).filter(active=True)
        if not values["paginated"]:
            return Response(ReminderSerializer(records[:500], many=True).data)
        if values["q"]:
            records = records.filter(
                Q(title__icontains=values["q"]) | Q(source_entity__display_name__icontains=values["q"])
            )
        if values["domain"]:
            records = records.filter(domain=values["domain"])
        ordering = values["ordering"]
        records = records.order_by(ordering, "entity_id")
        count = records.count()
        page_size = int(values["page_size"])
        offset = (values["page"] - 1) * page_size
        selected = list(records[offset : offset + page_size + 1])
        return Response(ReminderResultSerializer({
            "results": selected[:page_size],
            "count": count,
            "page": values["page"],
            "page_size": page_size,
            "has_more": len(selected) > page_size,
        }).data)

    @extend_schema(request=ReminderWriteSerializer, responses={201: ReminderSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DEADLINES_EDIT, organization=workspace.organization)
        serializer = ReminderWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reminder = create_reminder(
                workspace=workspace,
                actor_id=request.user.pk,
                value=ReminderInput(**serializer.validated_data),
            )
        except ReminderError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(ReminderSerializer(reminder).data, status=201)


class ReminderCalendarView(APIView):
    @extend_schema(responses={(200, "text/calendar"): bytes})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DEADLINES_VIEW, organization=workspace.organization)
        response = HttpResponse(calendar_bytes(workspace=workspace), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="tekdocs-deadlines.ics"'
        response["Cache-Control"] = "private, no-store"
        return response


@extend_schema_view(
    get=extend_schema(operation_id="msp_reminder_list"),
    post=extend_schema(operation_id="msp_reminder_create"),
)
class MSPReminderListCreateView(ReminderListCreateView):
    pass


@extend_schema_view(get=extend_schema(operation_id="msp_reminder_calendar"))
class MSPReminderCalendarView(ReminderCalendarView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_reminder_list"),
    post=extend_schema(operation_id="organization_reminder_create"),
)
class OrganizationReminderListCreateView(ReminderListCreateView):
    pass


@extend_schema_view(get=extend_schema(operation_id="organization_reminder_calendar"))
class OrganizationReminderCalendarView(ReminderCalendarView):
    pass
