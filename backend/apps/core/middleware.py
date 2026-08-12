import re
import uuid
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse

from .models import InstallationState, Organization, Tenant
from .rls import OrganizationRLSMode, bind_local_rls_scope
from .scoping import DataScope


class RequestContextMiddleware:
    IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,199}$")

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = uuid.uuid4()
        request.request_id = request_id  # type: ignore[attr-defined]
        idempotency_key = request.headers.get("Idempotency-Key")
        response: HttpResponse
        if idempotency_key is not None and not self.IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            response = JsonResponse(
                {
                    "error": {
                        "status": 400,
                        "code": "invalid_idempotency_key",
                        "message": "The request is invalid.",
                        "fields": {
                            "Idempotency-Key": [
                                "Use 8–200 ASCII letters, numbers, periods, underscores, colons, or hyphens."
                            ]
                        },
                        "request_id": str(request_id),
                    }
                },
                status=400,
            )
        else:
            request.idempotency_key = idempotency_key  # type: ignore[attr-defined]
            response = self.get_response(request)
        response["X-Request-ID"] = str(request_id)
        if idempotency_key is not None and response.status_code < 500:
            response["Idempotency-Key"] = idempotency_key
        return response


class SecurityHeadersMiddleware:
    POLICY = "; ".join(
        (
            "default-src 'self'",
            "base-uri 'self'",
            "connect-src 'self'",
            "font-src 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "img-src 'self' data:",
            "object-src 'none'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
        )
    )

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.POLICY)
        response.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        return response


class RLSRequestScopeMiddleware:
    """Bind one transaction-local database scope around authenticated requests."""

    ORGANIZATION_ROUTE_ARGUMENT = "organization_entity_id"

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        has_session = settings.SESSION_COOKIE_NAME in request.COOKIES
        has_api_token = getattr(request, "api_token", None) is not None
        if connection.vendor != "postgresql" or not (has_session or has_api_token):
            return self.get_response(request)

        with transaction.atomic():
            if request.user.is_authenticated:
                state = (
                    InstallationState.objects.select_related("tenant")
                    .filter(pk=InstallationState.SINGLETON_ID, bootstrapped_at__isnull=False)
                    .first()
                )
                if state is not None and state.tenant is not None:
                    request.rls_tenant = state.tenant  # type: ignore[attr-defined]
                    tenant_scope = DataScope.tenant(state.tenant)
                    bind_local_rls_scope(tenant_scope, organization_mode=OrganizationRLSMode.MSP_ONLY)
            return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., HttpResponse],
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        del view_func, view_args
        tenant: Tenant | None = getattr(request, "rls_tenant", None)
        organization_entity_id = view_kwargs.get(self.ORGANIZATION_ROUTE_ARGUMENT)
        if tenant is None or organization_entity_id is None:
            return None
        organization = Organization.objects.filter(
            tenant=tenant,
            entity_id=organization_entity_id,
            entity__archived_at__isnull=True,
        ).first()
        if organization is not None:
            bind_local_rls_scope(
                DataScope.organization(tenant, organization),
                organization_mode=OrganizationRLSMode.ORGANIZATION,
            )
        return None
