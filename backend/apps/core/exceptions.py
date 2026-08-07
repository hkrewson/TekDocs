from rest_framework.views import exception_handler


def api_exception_handler(exc, context):  # type: ignore[no-untyped-def]
    response = exception_handler(exc, context)
    if response is None:
        return None
    request = context.get("request")
    request_id = getattr(request, "request_id", None)
    response.data = {
        "error": {
            "status": response.status_code,
            "detail": response.data,
            "request_id": str(request_id) if request_id else None,
        }
    }
    return response
