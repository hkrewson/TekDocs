import secrets
from typing import Any

from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import InstallationState

from .bootstrap import bootstrap_owner
from .serializers import BootstrapStatusSerializer, OwnerBootstrapResultSerializer, OwnerBootstrapSerializer

BOOTSTRAP_AUTH_HEADER = "X-TekDocs-Bootstrap-Token"


class BootstrapStatusView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: BootstrapStatusSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        required = InstallationState.objects.filter(
            pk=InstallationState.SINGLETON_ID,
            bootstrapped_at__isnull=True,
        ).exists()
        return Response({"bootstrap_required": required})


class OwnerBootstrapView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=OwnerBootstrapSerializer,
        parameters=[
            OpenApiParameter(
                name=BOOTSTRAP_AUTH_HEADER,
                type=str,
                location=OpenApiParameter.HEADER,
                required=True,
                description="High-entropy deployment bootstrap secret",
            )
        ],
        responses={
            201: OwnerBootstrapResultSerializer,
            400: OpenApiResponse(description="Invalid bootstrap details"),
            403: OpenApiResponse(description="Bootstrap authorization failed"),
            409: OpenApiResponse(description="Installation already bootstrapped or not pristine"),
        },
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        configured_token = settings.TEKDOCS_BOOTSTRAP_TOKEN
        supplied_token = request.headers.get(BOOTSTRAP_AUTH_HEADER, "")
        if not configured_token or not secrets.compare_digest(supplied_token, configured_token):
            raise PermissionDenied("Bootstrap authorization failed.")

        serializer = OwnerBootstrapSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = bootstrap_owner(**serializer.validated_data)
        return Response(
            {
                "tenant": {"id": str(result.tenant.id), "name": result.tenant.name},
                "owner": {"id": str(result.owner.id), "display_name": result.owner.display_name},
            },
            status=201,
        )
