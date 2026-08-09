import uuid
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse

from .models import InstallationState, Organization, Tenant
from .rls import OrganizationRLSMode, bind_local_rls_scope
from .scoping import DataScope


class RequestContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = uuid.uuid4()
        request.request_id = request_id  # type: ignore[attr-defined]
        response = self.get_response(request)
        response["X-Request-ID"] = str(request_id)
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
        if connection.vendor != "postgresql" or settings.SESSION_COOKIE_NAME not in request.COOKIES:
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
