from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import serializers


class ApiErrorSerializer(serializers.Serializer):
    status = serializers.IntegerField(min_value=400, max_value=599)
    code = serializers.CharField(max_length=100)
    message = serializers.CharField(max_length=500)
    fields = serializers.DictField(child=serializers.ListField(child=serializers.CharField()), required=False)
    detail = serializers.JSONField(required=False, help_text="Deprecated compatibility detail; use message and fields.")
    request_id = serializers.UUIDField()


class ApiErrorEnvelopeSerializer(serializers.Serializer):
    error = ApiErrorSerializer()


class ApiRootSerializer(serializers.Serializer):
    name = serializers.CharField()
    version = serializers.CharField()
    status = serializers.CharField()
    api_version = serializers.CharField()
    schema_url = serializers.CharField()
    documentation_url = serializers.CharField()
    conventions = serializers.DictField()


IDEMPOTENCY_KEY_PARAMETER = OpenApiParameter(
    name="Idempotency-Key",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "An opaque 8–200 character retry key. It is meaningful only on operations that explicitly declare it; "
        "such operations return the same domain outcome when retried with the same request semantics."
    ),
)


def public_api_postprocessing(result, generator, request, public):  # type: ignore[no-untyped-def]
    """Attach cross-cutting response/error components without changing domain schemas."""

    del generator, request, public
    schemas = result.setdefault("components", {}).setdefault("schemas", {})
    schemas.setdefault(
        "ApiError",
        {
            "type": "object",
            "required": ["status", "code", "message", "request_id"],
            "properties": {
                "status": {"type": "integer", "minimum": 400, "maximum": 599},
                "code": {"type": "string", "maxLength": 100},
                "message": {"type": "string", "maxLength": 500},
                "fields": {
                    "type": "object",
                    "additionalProperties": {"type": "array", "items": {"type": "string"}},
                },
                "detail": {"description": "Deprecated compatibility detail; use message and fields."},
                "request_id": {"type": "string", "format": "uuid"},
            },
        },
    )
    schemas.setdefault(
        "ApiErrorEnvelope",
        {
            "type": "object",
            "required": ["error"],
            "properties": {"error": {"$ref": "#/components/schemas/ApiError"}},
        },
    )
    response_header = {
        "description": "Server-generated request correlation UUID.",
        "schema": {"type": "string", "format": "uuid"},
    }
    for path, path_item in result.get("paths", {}).items():
        if not path.startswith("/api/v1"):
            continue
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for status, response in operation.get("responses", {}).items():
                if "$ref" in response:
                    continue
                response.setdefault("headers", {}).setdefault("X-Request-ID", response_header)
                if str(status).startswith(("4", "5")):
                    response.setdefault("content", {}).setdefault(
                        "application/json", {"schema": {"$ref": "#/components/schemas/ApiErrorEnvelope"}}
                    )
    return result
