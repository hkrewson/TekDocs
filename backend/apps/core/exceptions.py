from typing import Any

from rest_framework.views import exception_handler


def _message(status: int) -> str:
    return {
        400: "The request is invalid.",
        401: "Authentication is required.",
        403: "The request is not authorized.",
        404: "The requested resource is unavailable.",
        405: "The method is not supported.",
        409: "The request conflicts with current state.",
        410: "The requested resource is no longer available.",
        415: "The content type is not supported.",
        429: "Too many requests.",
    }.get(status, "The request could not be completed.")


def _field_errors(detail: Any) -> dict[str, list[str]] | None:
    if not isinstance(detail, dict):
        return None
    fields: dict[str, list[str]] = {}
    for name, value in detail.items():
        values = value if isinstance(value, list) else [value]
        fields[str(name)] = [str(item) for item in values]
    return fields


def api_exception_handler(exc, context):  # type: ignore[no-untyped-def]
    response = exception_handler(exc, context)
    if response is None:
        return None
    request = context.get("request")
    request_id = getattr(request, "request_id", None)
    codes = exc.get_codes() if hasattr(exc, "get_codes") else "error"
    code = codes if isinstance(codes, str) else "validation_error"
    error = {
        "status": response.status_code,
        "code": code,
        "message": _message(response.status_code),
        "detail": response.data,
        "request_id": str(request_id),
    }
    fields = _field_errors(response.data)
    if fields is not None:
        error["fields"] = fields
    response.data = {"error": error}
    return response
