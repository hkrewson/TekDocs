from typing import Any

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, extend_schema_view
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
    domain = serializers.ChoiceField(choices=("compliance", "inventory", "domain"))
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


def _workspace(request: Any, organization_entity_id: Any = None) -> ResolvedWorkspace:
    return (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id
        else resolve_msp_workspace(request.user)
    )


class ReminderListCreateView(APIView):
    @extend_schema(responses={200: ReminderSerializer(many=True)})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DEADLINES_VIEW, organization=workspace.organization)
        return Response(ReminderSerializer(reminders_for_scope(workspace).filter(active=True)[:500], many=True).data)

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
