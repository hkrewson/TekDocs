from typing import Any

from django.conf import settings
from django.db import connection
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission
from apps.core.api_contracts import ApiRootSerializer, SystemDiagnosticsSerializer
from apps.core.diagram_exports import diagram_renderer_diagnostics, diagram_renderer_health
from apps.core.models import InstallationState
from tekdocs.version import VERSION


class ApiRootView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: ApiRootSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        return Response(
            {
                "name": "TekDocs API",
                "version": VERSION,
                "status": "pre-alpha",
                "api_version": "v1",
                "schema_url": "/api/v1/schema/",
                "documentation_url": "/api/v1/docs/",
                "conventions": {
                    "pagination": {
                        "offset": ["results", "page", "page_size", "count", "has_more"],
                        "seek": ["results", "has_more", "next_cursor"],
                        "maximum_page_size": 100,
                    },
                    "filtering": "Only documented query parameters are accepted; unknown filters return 400.",
                    "errors": ["status", "code", "message", "fields", "request_id"],
                    "idempotency": (
                        "Keys are bounded and echoed for correlation; retry semantics apply only to operations "
                        "that declare Idempotency-Key in OpenAPI."
                    ),
                },
            }
        )


class LiveHealthView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict})
    def get(self, request):  # type: ignore[no-untyped-def]
        return Response({"status": "ok", "service": "backend", "version": VERSION})


class ReadyHealthView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict, 503: dict})
    def get(self, request):  # type: ignore[no-untyped-def]
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:  # noqa: BLE001
            return Response({"status": "unavailable", "database": "unavailable"}, status=503)
        renderer = diagram_renderer_health()
        renderer_status = {} if renderer == "not_configured" else {"diagram_renderer": renderer}
        if renderer not in {"not_configured", "ready"}:
            return Response(
                {"status": "unavailable", "database": "ready", **renderer_status, "version": VERSION},
                status=503,
            )
        bootstrap_required = InstallationState.objects.filter(
            pk=InstallationState.SINGLETON_ID, bootstrapped_at__isnull=True
        ).exists()
        if bootstrap_required and not settings.TEKDOCS_BOOTSTRAP_TOKEN:
            return Response(
                {
                    "status": "unavailable",
                    "database": "ready",
                    "bootstrap": "unavailable",
                    **renderer_status,
                    "version": VERSION,
                },
                status=503,
            )
        return Response({"status": "ok", "database": "ready", **renderer_status, "version": VERSION})


class SystemDiagnosticsView(APIView):
    @extend_schema(responses={200: SystemDiagnosticsSerializer, 403: dict})
    def get(self, request):  # type: ignore[no-untyped-def]
        require_permission(request.user, PermissionKey.SYSTEM_DIAGNOSTICS_VIEW)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        renderer = diagram_renderer_diagnostics()
        return Response(
            {
                "status": "ready" if renderer["status"] == "ready" else "degraded",
                "checked_at": timezone.now(),
                "application_version": VERSION,
                "database": "ready",
                "diagram_renderer": renderer,
            }
        )
