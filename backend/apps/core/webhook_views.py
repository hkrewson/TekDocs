from __future__ import annotations

from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .collection_pagination import BoundedCollectionQuerySerializer, OffsetPageSerializer, paginate
from .models import WebhookDeliveryState, WebhookDirection, WebhookEndpoint
from .outbox import OutboxTopic
from .webhook_egress import MAX_WEBHOOK_BODY_BYTES
from .webhooks import (
    accept_inbound_webhook,
    authorize_webhook_management,
    create_webhook_endpoint,
    deliveries_for_organization,
    endpoints_for_organization,
    retry_webhook_delivery,
    rotate_webhook_secret,
    set_webhook_endpoint_active,
)


class WebhookEndpointSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    direction = serializers.ChoiceField(choices=WebhookDirection.choices)
    name = serializers.CharField()
    url = serializers.CharField()
    inbound_path = serializers.SerializerMethodField()
    topics = serializers.ListField(child=serializers.CharField())
    secret_prefix = serializers.CharField()
    secret_generation = serializers.IntegerField()
    active = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_inbound_path(self, endpoint: WebhookEndpoint) -> str | None:
        return f"/api/v1/webhooks/inbound/{endpoint.id}" if endpoint.direction == WebhookDirection.INBOUND else None


class IssuedWebhookEndpointSerializer(WebhookEndpointSerializer):
    signing_secret = serializers.CharField()


class WebhookEndpointWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=100, trim_whitespace=True)
    direction = serializers.ChoiceField(choices=WebhookDirection.choices)
    url = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)
    topics = serializers.ListField(child=serializers.CharField(max_length=120), min_length=1, max_length=20)


class WebhookEndpointActiveSerializer(serializers.Serializer):
    active = serializers.BooleanField()


class WebhookDeliverySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    endpoint_id = serializers.UUIDField()
    endpoint_name = serializers.CharField(source="endpoint.name")
    topic = serializers.CharField(source="event.topic")
    state = serializers.ChoiceField(choices=WebhookDeliveryState.choices)
    attempts = serializers.IntegerField()
    available_at = serializers.DateTimeField()
    last_attempt_at = serializers.DateTimeField(allow_null=True)
    delivered_at = serializers.DateTimeField(allow_null=True)
    response_status = serializers.IntegerField(allow_null=True)
    last_error_code = serializers.CharField()
    created_at = serializers.DateTimeField()


class WebhookDeliveryResultSerializer(OffsetPageSerializer):
    results = WebhookDeliverySerializer(many=True)


class WebhookDeliveryQuerySerializer(BoundedCollectionQuerySerializer):
    state = serializers.ChoiceField(choices=WebhookDeliveryState.choices, required=False)
    endpoint_id = serializers.UUIDField(required=False)
    topic = serializers.ChoiceField(choices=[topic.value for topic in OutboxTopic], required=False)


class WebhookRetrySerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=200, trim_whitespace=True)


class InboundWebhookResponseSerializer(serializers.Serializer):
    accepted = serializers.BooleanField()
    receipt_id = serializers.UUIDField()


def _issued_payload(endpoint: WebhookEndpoint, secret: str) -> dict[str, object]:
    payload = dict(WebhookEndpointSerializer(endpoint).data)
    payload["signing_secret"] = secret
    return payload


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    response["Pragma"] = "no-cache"
    return response


class OrganizationWebhookEndpointListCreateView(APIView):
    authentication_classes = [SessionAuthentication]

    @extend_schema(responses={200: WebhookEndpointSerializer(many=True)})
    def get(self, request: Request, organization_entity_id: UUID) -> Response:
        _organization, endpoints = endpoints_for_organization(
            user=request.user, organization_entity_id=organization_entity_id
        )
        return _private(Response(WebhookEndpointSerializer(endpoints, many=True).data))

    @extend_schema(
        request=WebhookEndpointWriteSerializer,
        responses={
            201: IssuedWebhookEndpointSerializer,
            403: OpenApiResponse(description="Recent MFA session required"),
        },
    )
    def post(self, request: Request, organization_entity_id: UUID) -> Response:
        authorize_webhook_management(request=request, organization_entity_id=organization_entity_id)
        serializer = WebhookEndpointWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        endpoint, secret = create_webhook_endpoint(
            request=request,
            organization_entity_id=organization_entity_id,
            name=serializer.validated_data["name"],
            direction=WebhookDirection(serializer.validated_data["direction"]),
            url=serializer.validated_data["url"],
            topics=serializer.validated_data["topics"],
        )
        return _private(Response(_issued_payload(endpoint, secret), status=201))


class OrganizationWebhookEndpointDetailView(APIView):
    authentication_classes = [SessionAuthentication]

    @extend_schema(request=WebhookEndpointActiveSerializer, responses={200: WebhookEndpointSerializer})
    def patch(self, request: Request, organization_entity_id: UUID, endpoint_id: UUID) -> Response:
        authorize_webhook_management(request=request, organization_entity_id=organization_entity_id)
        serializer = WebhookEndpointActiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        endpoint = set_webhook_endpoint_active(
            request=request,
            organization_entity_id=organization_entity_id,
            endpoint_id=endpoint_id,
            active=serializer.validated_data["active"],
        )
        return _private(Response(WebhookEndpointSerializer(endpoint).data))


class OrganizationWebhookEndpointRotateView(APIView):
    authentication_classes = [SessionAuthentication]

    @extend_schema(request=None, responses={200: IssuedWebhookEndpointSerializer})
    def post(self, request: Request, organization_entity_id: UUID, endpoint_id: UUID) -> Response:
        endpoint, secret = rotate_webhook_secret(
            request=request,
            organization_entity_id=organization_entity_id,
            endpoint_id=endpoint_id,
        )
        return _private(Response(_issued_payload(endpoint, secret)))


class OrganizationWebhookDeliveryListView(APIView):
    authentication_classes = [SessionAuthentication]

    @extend_schema(parameters=[WebhookDeliveryQuerySerializer], responses={200: WebhookDeliveryResultSerializer})
    def get(self, request: Request, organization_entity_id: UUID) -> Response:
        serializer = WebhookDeliveryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        _organization, records = deliveries_for_organization(
            user=request.user, organization_entity_id=organization_entity_id
        )
        if state := serializer.validated_data.get("state"):
            records = records.filter(state=state)
        if endpoint_id := serializer.validated_data.get("endpoint_id"):
            records = records.filter(endpoint_id=endpoint_id)
        if topic := serializer.validated_data.get("topic"):
            records = records.filter(event__topic=topic)
        page = paginate(
            records,
            page=serializer.validated_data["page"],
            page_size=serializer.validated_data["page_size"],
        )
        return _private(
            Response(
                WebhookDeliveryResultSerializer(
                    {
                        "results": WebhookDeliverySerializer(page.records, many=True).data,
                        "page": page.page,
                        "page_size": page.page_size,
                        "count": page.count,
                        "has_more": page.has_more,
                    }
                ).data
            )
        )


class OrganizationWebhookDeliveryRetryView(APIView):
    authentication_classes = [SessionAuthentication]

    @extend_schema(request=WebhookRetrySerializer, responses={200: WebhookDeliverySerializer})
    def post(self, request: Request, organization_entity_id: UUID, delivery_id: UUID) -> Response:
        authorize_webhook_management(request=request, organization_entity_id=organization_entity_id)
        serializer = WebhookRetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delivery = retry_webhook_delivery(
            request=request,
            organization_entity_id=organization_entity_id,
            delivery_id=delivery_id,
            reason=serializer.validated_data["reason"],
        )
        return _private(Response(WebhookDeliverySerializer(delivery).data))


class InboundWebhookView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={
            202: InboundWebhookResponseSerializer,
            403: OpenApiResponse(description="Invalid or replayed signature"),
        },
    )
    def post(self, request: Request, endpoint_id: UUID) -> Response:
        content_length = request.META.get("CONTENT_LENGTH", "")
        try:
            declared_length = int(content_length) if content_length else 0
        except ValueError as exc:
            raise serializers.ValidationError({"body": "The request body length is invalid."}) from exc
        if declared_length > MAX_WEBHOOK_BODY_BYTES:
            raise serializers.ValidationError({"body": "The request body is too large."})
        body = request.stream.read(MAX_WEBHOOK_BODY_BYTES + 1)
        if len(body) > MAX_WEBHOOK_BODY_BYTES:
            raise serializers.ValidationError({"body": "The request body is too large."})
        receipt = accept_inbound_webhook(
            endpoint_id=endpoint_id,
            delivery_id=request.headers.get("TekDocs-Webhook-Id", ""),
            timestamp_value=request.headers.get("TekDocs-Webhook-Timestamp", ""),
            supplied_signature=request.headers.get("TekDocs-Webhook-Signature", ""),
            body=body,
        )
        response = Response({"accepted": True, "receipt_id": receipt.id}, status=202)
        response["Cache-Control"] = "no-store"
        return response
