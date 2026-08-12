from uuid import UUID

from django.http import Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import InstallationMemberContext, require_client_portal_member, require_installation_member

from .models import InboxNotification, NotificationSurface
from .notifications import (
    NotificationProjection,
    authorize_notification,
    notification_candidates,
    set_notification_read,
)


class NotificationTargetSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=("organization_overview", "organization_documentation", "portal_documents", "portal_document")
    )
    organization_id = serializers.UUIDField(allow_null=True)
    publication_id = serializers.UUIDField(allow_null=True)


class InboxNotificationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    topic = serializers.CharField()
    title = serializers.CharField()
    message = serializers.CharField()
    read = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    target = NotificationTargetSerializer(allow_null=True)


class InboxNotificationResultSerializer(serializers.Serializer):
    results = InboxNotificationSerializer(many=True)
    unread_count = serializers.IntegerField(min_value=0)
    has_more = serializers.BooleanField()


class InboxNotificationReadSerializer(serializers.Serializer):
    read = serializers.BooleanField()


def _serialized_projection(projection: NotificationProjection) -> dict[str, object]:
    notification = projection.notification
    target = projection.target
    return {
        "id": notification.id,
        "topic": notification.event.topic,
        "title": projection.title,
        "message": projection.message,
        "read": notification.read_at is not None,
        "created_at": notification.created_at,
        "target": (
            {
                "kind": target.kind,
                "organization_id": target.organization_id,
                "publication_id": target.publication_id,
            }
            if target is not None
            else None
        ),
    }


class NotificationSurfaceMixin:
    surface: NotificationSurface

    def context(self, request: Request) -> InstallationMemberContext:
        context = (
            require_client_portal_member(request.user)
            if self.surface == NotificationSurface.CLIENT_PORTAL
            else require_installation_member(request.user)
        )
        if context.surface != self.surface:
            raise Http404
        return context


class NotificationListView(NotificationSurfaceMixin, APIView):
    def get(self, request: Request) -> Response:
        context = self.context(request)
        projections = [
            projection
            for notification in notification_candidates(context)
            if (projection := authorize_notification(notification, context)) is not None
        ]
        response = Response(
            InboxNotificationResultSerializer(
                {
                    "results": [_serialized_projection(item) for item in projections[:50]],
                    "unread_count": sum(item.notification.read_at is None for item in projections),
                    "has_more": len(projections) > 50,
                }
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response


class NotificationReadView(NotificationSurfaceMixin, APIView):
    def patch(self, request: Request, notification_id: UUID) -> Response:
        context = self.context(request)
        serializer = InboxNotificationReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notification = (
            InboxNotification.scoped.for_tenant(context.tenant)
            .filter(id=notification_id, recipient=context.user, surface=self.surface)
            .select_related("event", "organization")
            .first()
        )
        if notification is None or (projection := authorize_notification(notification, context)) is None:
            raise Http404
        set_notification_read(notification, read=serializer.validated_data["read"])
        projection = authorize_notification(notification, context)
        if projection is None:
            raise Http404
        response = Response(InboxNotificationSerializer(_serialized_projection(projection)).data)
        response["Cache-Control"] = "private, no-store"
        return response


class MSPNotificationListView(NotificationListView):
    surface = NotificationSurface.MSP

    @extend_schema(operation_id="msp_notifications_list", responses={200: InboxNotificationResultSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        return super().get(request)


class MSPNotificationReadView(NotificationReadView):
    surface = NotificationSurface.MSP

    @extend_schema(
        operation_id="msp_notifications_read_update",
        request=InboxNotificationReadSerializer,
        responses={200: InboxNotificationSerializer, 404: OpenApiResponse(description="Notification unavailable")},
    )
    def patch(self, request, notification_id: UUID):  # type: ignore[no-untyped-def]
        return super().patch(request, notification_id)


class ClientPortalNotificationListView(NotificationListView):
    surface = NotificationSurface.CLIENT_PORTAL

    @extend_schema(operation_id="client_portal_notifications_list", responses={200: InboxNotificationResultSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        return super().get(request)


class ClientPortalNotificationReadView(NotificationReadView):
    surface = NotificationSurface.CLIENT_PORTAL

    @extend_schema(
        operation_id="client_portal_notifications_read_update",
        request=InboxNotificationReadSerializer,
        responses={200: InboxNotificationSerializer, 404: OpenApiResponse(description="Notification unavailable")},
    )
    def patch(self, request, notification_id: UUID):  # type: ignore[no-untyped-def]
        return super().patch(request, notification_id)
