from typing import Any

from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class ApiRootView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict})
    def get(self, request):  # type: ignore[no-untyped-def]
        return Response({"name": "TekDocs API", "version": "0.0.8", "status": "pre-alpha"})


class LiveHealthView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict})
    def get(self, request):  # type: ignore[no-untyped-def]
        return Response({"status": "ok", "service": "backend", "version": "0.0.8"})


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
        return Response({"status": "ok", "database": "ready", "version": "0.0.8"})
