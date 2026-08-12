from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import (
    InstallationMemberContext,
    PermissionKey,
    require_client_portal_member,
    require_installation_member,
    require_permission,
)

from .models import (
    AuditEvent,
    InboxNotification,
    NotificationEmailDelivery,
    NotificationEmailState,
    NotificationPreference,
    NotificationSurface,
)
from .notification_email import preference_for
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


class NotificationPreferenceSerializer(serializers.Serializer):
    email_enabled = serializers.BooleanField()
    invitation_events = serializers.BooleanField()
    publication_events = serializers.BooleanField()
    delivery_mode = serializers.ChoiceField(choices=("immediate", "hourly", "daily"))
    timezone = serializers.CharField(max_length=64)
    quiet_start = serializers.TimeField(allow_null=True)
    quiet_end = serializers.TimeField(allow_null=True)
    daily_digest_hour = serializers.IntegerField(min_value=0, max_value=23)

    def validate_timezone(self, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise serializers.ValidationError("Use a valid IANA time-zone name.") from exc
        return value

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        instance = self.instance
        start = attrs.get("quiet_start", getattr(instance, "quiet_start", None))
        end = attrs.get("quiet_end", getattr(instance, "quiet_end", None))
        if (start is None) != (end is None):
            raise serializers.ValidationError("Quiet hours require both a start and end time.")
        if start is not None and start == end:
            raise serializers.ValidationError("Quiet-hour start and end must differ.")
        return attrs


def _preference_payload(preference: NotificationPreference) -> dict[str, object]:
    return {
        "email_enabled": preference.email_enabled,
        "invitation_events": preference.invitation_events,
        "publication_events": preference.publication_events,
        "delivery_mode": preference.delivery_mode,
        "timezone": preference.timezone,
        "quiet_start": preference.quiet_start,
        "quiet_end": preference.quiet_end,
        "daily_digest_hour": preference.daily_digest_hour,
    }


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


class NotificationPreferenceView(NotificationSurfaceMixin, APIView):
    def get(self, request: Request) -> Response:
        context = self.context(request)
        preference = preference_for(tenant=context.tenant, user_id=context.user.id, surface=self.surface)
        response = Response(NotificationPreferenceSerializer(_preference_payload(preference)).data)
        response["Cache-Control"] = "private, no-store"
        return response

    def patch(self, request: Request) -> Response:
        context = self.context(request)
        preference = preference_for(tenant=context.tenant, user_id=context.user.id, surface=self.surface)
        serializer = NotificationPreferenceSerializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(preference, field, value)
        preference.save()
        response = Response(NotificationPreferenceSerializer(_preference_payload(preference)).data)
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


class MSPNotificationPreferenceView(NotificationPreferenceView):
    surface = NotificationSurface.MSP

    @extend_schema(
        operation_id="msp_notification_preferences_retrieve",
        responses={200: NotificationPreferenceSerializer},
    )
    def get(self, request: Request) -> Response:
        return super().get(request)

    @extend_schema(
        operation_id="msp_notification_preferences_update",
        request=NotificationPreferenceSerializer,
        responses={200: NotificationPreferenceSerializer},
    )
    def patch(self, request: Request) -> Response:
        return super().patch(request)


class ClientPortalNotificationPreferenceView(NotificationPreferenceView):
    surface = NotificationSurface.CLIENT_PORTAL

    @extend_schema(
        operation_id="client_portal_notification_preferences_retrieve",
        responses={200: NotificationPreferenceSerializer},
    )
    def get(self, request: Request) -> Response:
        return super().get(request)

    @extend_schema(
        operation_id="client_portal_notification_preferences_update",
        request=NotificationPreferenceSerializer,
        responses={200: NotificationPreferenceSerializer},
    )
    def patch(self, request: Request) -> Response:
        return super().patch(request)


class NotificationDeliverySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    state = serializers.CharField()
    surface = serializers.CharField()
    attempts = serializers.IntegerField()
    retry_generation = serializers.IntegerField()
    event_topic = serializers.CharField()
    organization = serializers.CharField()
    recipient = serializers.CharField()
    created_at = serializers.DateTimeField()
    available_at = serializers.DateTimeField()
    last_attempt_at = serializers.DateTimeField(allow_null=True)
    delivered_at = serializers.DateTimeField(allow_null=True)
    last_error_code = serializers.CharField()


class NotificationDeliveryRetrySerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=240, trim_whitespace=True)


def _delivery_payload(delivery: NotificationEmailDelivery) -> dict[str, object]:
    return {
        "id": delivery.id,
        "state": delivery.state,
        "surface": delivery.surface,
        "attempts": delivery.attempts,
        "retry_generation": delivery.retry_generation,
        "event_topic": delivery.notification.event.topic,
        "organization": delivery.organization.entity.display_name,
        "recipient": delivery.recipient.display_name,
        "created_at": delivery.created_at,
        "available_at": delivery.available_at,
        "last_attempt_at": delivery.last_attempt_at,
        "delivered_at": delivery.delivered_at,
        "last_error_code": delivery.last_error_code,
    }


class NotificationDeliveryAdminListView(APIView):
    @extend_schema(
        operation_id="notification_deliveries_list", responses={200: NotificationDeliverySerializer(many=True)}
    )
    def get(self, request: Request) -> Response:
        context = require_permission(request.user, PermissionKey.NOTIFICATIONS_MANAGE)
        state = request.query_params.get("state")
        if state and state not in NotificationEmailState.values:
            raise serializers.ValidationError({"state": "Select a valid delivery state."})
        deliveries = (
            NotificationEmailDelivery.scoped.for_tenant(context.tenant)
            .select_related("notification__event", "organization__entity", "recipient")
            .order_by("-created_at", "-id")
        )
        if state:
            deliveries = deliveries.filter(state=state)
        response = Response(
            NotificationDeliverySerializer([_delivery_payload(item) for item in deliveries[:100]], many=True).data
        )
        response["Cache-Control"] = "private, no-store"
        return response


class NotificationDeliveryAdminRetryView(APIView):
    @extend_schema(
        operation_id="notification_deliveries_retry",
        request=NotificationDeliveryRetrySerializer,
        responses={200: NotificationDeliverySerializer, 404: OpenApiResponse(description="Delivery unavailable")},
    )
    def post(self, request: Request, delivery_id: UUID) -> Response:
        context = require_permission(request.user, PermissionKey.NOTIFICATIONS_MANAGE)
        serializer = NotificationDeliveryRetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            delivery = (
                NotificationEmailDelivery.scoped.for_tenant(context.tenant)
                .select_for_update()
                .select_related("notification__event", "organization__entity", "recipient")
                .filter(pk=delivery_id, state=NotificationEmailState.DEAD_LETTER)
                .first()
            )
            if delivery is None:
                raise Http404
            generation = delivery.retry_generation + 1
            AuditEvent.objects.create(
                tenant=context.tenant,
                actor=request.user,
                action="notification.delivery_retried",
                entity_id=delivery.id,
                metadata={"generation": generation, "reason": serializer.validated_data["reason"]},
            )
            delivery.state = NotificationEmailState.PENDING
            delivery.attempts = 0
            delivery.retry_generation = generation
            delivery.available_at = timezone.now()
            delivery.locked_at = None
            delivery.delivered_at = None
            delivery.last_attempt_at = None
            delivery.last_error_code = ""
            delivery.save(
                update_fields=(
                    "state",
                    "attempts",
                    "retry_generation",
                    "available_at",
                    "locked_at",
                    "delivered_at",
                    "last_attempt_at",
                    "last_error_code",
                )
            )
        response = Response(NotificationDeliverySerializer(_delivery_payload(delivery)).data)
        response["Cache-Control"] = "private, no-store"
        return response
