from typing import Any

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policy import PermissionKey, require_permission

from .certificate_monitoring import (
    CertificateMonitoringError,
    create_certificate_endpoint,
    endpoints_for_domain,
    enqueue_certificate_monitoring,
)
from .domain_monitoring import enqueue_domain_monitoring, monitoring_runs_for_domain
from .domains import DomainError, DomainInput, create_domain, domains_for_scope, review_domain
from .models import (
    CertificateEndpoint,
    CertificateMonitorAlert,
    CertificateMonitorRun,
    DomainMonitorAlert,
    ManagedHostname,
    RegisteredDomain,
)
from .workspaces import ResolvedWorkspace, resolve_msp_workspace, resolve_organization_workspace


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):  # type: ignore[no-untyped-def]
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        return super().to_internal_value(data)


class DomainWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=253)
    registrar_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    registration_date = serializers.DateField(required=False, allow_null=True, default=None)
    expiration_date = serializers.DateField(required=False, allow_null=True, default=None)
    renewal_mode = serializers.ChoiceField(choices=("manual", "auto", "external"))
    owner_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    status = serializers.ChoiceField(choices=("active", "pending", "expired", "transferred"))
    notes = serializers.CharField(max_length=20_000, required=False, allow_blank=True, default="")


class DomainSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="ascii_name")
    registrar_id = serializers.UUIDField(source="registrar.entity_id", allow_null=True)
    registrar = serializers.CharField(source="registrar.name", allow_null=True)
    registration_date = serializers.DateField(allow_null=True)
    expiration_date = serializers.DateField(allow_null=True)
    renewal_mode = serializers.CharField()
    owner_id = serializers.UUIDField(allow_null=True)
    owner = serializers.CharField(source="owner.display_name", allow_null=True)
    status = serializers.CharField()
    notes = serializers.CharField()
    review_state = serializers.CharField()
    observed_expiration_date = serializers.DateField(allow_null=True)
    last_reviewed_at = serializers.DateTimeField(allow_null=True)
    monitoring_enabled = serializers.BooleanField()
    monitor_state = serializers.CharField()
    monitor_error_code = serializers.CharField()
    last_monitor_at = serializers.DateTimeField(allow_null=True)
    next_monitor_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()


def _workspace(request: Any, organization_entity_id: Any = None) -> ResolvedWorkspace:
    return (
        resolve_organization_workspace(request.user, entity_id=organization_entity_id)
        if organization_entity_id
        else resolve_msp_workspace(request.user)
    )


class DomainListCreateView(APIView):
    @extend_schema(responses={200: DomainSerializer(many=True)})
    def get(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_VIEW, organization=workspace.organization)
        return Response(DomainSerializer(domains_for_scope(workspace)[:500], many=True).data)

    @extend_schema(request=DomainWriteSerializer, responses={201: DomainSerializer})
    def post(self, request, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_EDIT, organization=workspace.organization)
        serializer = DomainWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            domain = create_domain(
                workspace=workspace, actor_id=request.user.pk, value=DomainInput(**serializer.validated_data)
            )
        except DomainError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(DomainSerializer(domain).data, status=201)


class DomainReviewSerializer(StrictSerializer):
    state = serializers.ChoiceField(choices=("current", "stale", "conflict"))
    observed_expiration_date = serializers.DateField(required=False, allow_null=True, default=None)
    source = serializers.CharField(max_length=120)
    note = serializers.CharField(max_length=20_000, required=False, allow_blank=True, default="")


class DomainReviewView(APIView):
    @extend_schema(request=DomainReviewSerializer, responses={200: DomainSerializer})
    def post(self, request, domain_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_EDIT, organization=workspace.organization)
        try:
            domain = RegisteredDomain.scoped.for_scope(workspace.data_scope).get(
                entity_id=domain_entity_id, archived_at__isnull=True
            )
        except RegisteredDomain.DoesNotExist as exc:
            raise serializers.ValidationError({"detail": "The selected domain is unavailable."}) from exc
        serializer = DomainReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            domain = review_domain(domain=domain, actor_id=request.user.pk, **serializer.validated_data)
        except DomainError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(DomainSerializer(domain).data)


class DomainMonitorRunSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    trigger = serializers.CharField()
    state = serializers.CharField()
    error_code = serializers.CharField()
    rdap_source = serializers.CharField()
    observed_expiration_date = serializers.DateField(allow_null=True)
    observed_registrar = serializers.CharField()
    dns_source = serializers.CharField()
    dnssec_validated = serializers.BooleanField(allow_null=True)
    dns_record_count = serializers.IntegerField()
    caa_record_count = serializers.IntegerField()
    evidence_digest = serializers.CharField()
    created_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)


class DomainMonitorAlertSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    observed_expiration_date = serializers.DateField(allow_null=True)
    prior_expiration_date = serializers.DateField(allow_null=True)
    created_at = serializers.DateTimeField()


class ManagedHostnameChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    name = serializers.CharField(source="ascii_name")


class DomainMonitoringView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request, domain_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_VIEW, organization=workspace.organization)
        try:
            domain = RegisteredDomain.scoped.for_scope(workspace.data_scope).get(
                entity_id=domain_entity_id, archived_at__isnull=True
            )
        except RegisteredDomain.DoesNotExist as exc:
            raise serializers.ValidationError({"detail": "The selected domain is unavailable."}) from exc
        runs = monitoring_runs_for_domain(workspace.data_scope, domain_entity_id)[:25]
        alerts = DomainMonitorAlert.scoped.for_scope(workspace.data_scope).filter(domain=domain)[:50]
        hostnames = ManagedHostname.scoped.for_scope(workspace.data_scope).filter(
            domain=domain, archived_at__isnull=True
        )[:500]
        return Response(
            {
                "domain": DomainSerializer(domain).data,
                "runs": DomainMonitorRunSerializer(runs, many=True).data,
                "alerts": DomainMonitorAlertSerializer(alerts, many=True).data,
                "hostnames": ManagedHostnameChoiceSerializer(hostnames, many=True).data,
            }
        )

    @extend_schema(request=None, responses={202: DomainMonitorRunSerializer})
    def post(self, request, domain_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_EDIT, organization=workspace.organization)
        try:
            domain = RegisteredDomain.scoped.for_scope(workspace.data_scope).get(
                entity_id=domain_entity_id, archived_at__isnull=True, monitoring_enabled=True
            )
        except RegisteredDomain.DoesNotExist as exc:
            raise serializers.ValidationError({"detail": "The selected domain is unavailable."}) from exc
        run = enqueue_domain_monitoring(
            scope=workspace.data_scope, domain=domain, requested_by_id=request.user.pk, trigger="manual"
        )
        return Response(DomainMonitorRunSerializer(run).data, status=202)


class CertificateEndpointWriteSerializer(StrictSerializer):
    protocol = serializers.ChoiceField(choices=("https", "smtps", "imaps", "pop3s"))
    hostname_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class CertificateEndpointSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="entity_id")
    domain_id = serializers.UUIDField(source="domain.entity_id")
    hostname_id = serializers.UUIDField(source="hostname.entity_id", allow_null=True)
    target_name = serializers.CharField()
    protocol = serializers.CharField()
    port = serializers.IntegerField()
    monitor_state = serializers.CharField()
    monitor_error_code = serializers.CharField()
    last_monitor_at = serializers.DateTimeField(allow_null=True)
    next_monitor_at = serializers.DateTimeField()
    current_leaf_sha256 = serializers.CharField()
    current_not_after = serializers.DateTimeField(allow_null=True)
    current_hostname_valid = serializers.BooleanField(allow_null=True)
    current_trust_valid = serializers.BooleanField(allow_null=True)


class CertificateMonitorRunSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    trigger = serializers.CharField()
    state = serializers.CharField()
    error_code = serializers.CharField()
    leaf_sha256 = serializers.CharField()
    chain_sha256 = serializers.CharField()
    chain_length = serializers.IntegerField()
    subject_common_name = serializers.CharField()
    issuer_common_name = serializers.CharField()
    san_count = serializers.IntegerField()
    not_before = serializers.DateTimeField(allow_null=True)
    not_after = serializers.DateTimeField(allow_null=True)
    hostname_valid = serializers.BooleanField(allow_null=True)
    trust_valid = serializers.BooleanField(allow_null=True)
    tls_version = serializers.CharField()
    cipher_name = serializers.CharField()
    evidence_digest = serializers.CharField()
    created_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)


class CertificateMonitorAlertSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    observed_not_after = serializers.DateTimeField(allow_null=True)
    prior_not_after = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


def _domain_for_certificate_request(workspace: ResolvedWorkspace, domain_entity_id: Any) -> RegisteredDomain:
    try:
        return RegisteredDomain.scoped.for_scope(workspace.data_scope).get(
            entity_id=domain_entity_id, archived_at__isnull=True
        )
    except RegisteredDomain.DoesNotExist as exc:
        raise serializers.ValidationError({"detail": "The selected domain is unavailable."}) from exc


class CertificateEndpointListCreateView(APIView):
    @extend_schema(responses={200: CertificateEndpointSerializer(many=True)})
    def get(self, request, domain_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_VIEW, organization=workspace.organization)
        domain = _domain_for_certificate_request(workspace, domain_entity_id)
        endpoints = endpoints_for_domain(workspace.data_scope, domain.entity_id)
        return Response(CertificateEndpointSerializer(endpoints, many=True).data)

    @extend_schema(request=CertificateEndpointWriteSerializer, responses={201: CertificateEndpointSerializer})
    def post(self, request, domain_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_EDIT, organization=workspace.organization)
        domain = _domain_for_certificate_request(workspace, domain_entity_id)
        serializer = CertificateEndpointWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            endpoint = create_certificate_endpoint(
                scope=workspace.data_scope, domain=domain, actor_id=request.user.pk, **serializer.validated_data
            )
        except CertificateMonitoringError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(CertificateEndpointSerializer(endpoint).data, status=201)


class CertificateMonitoringView(APIView):
    def _endpoint(
        self, workspace: ResolvedWorkspace, domain_entity_id: Any, endpoint_entity_id: Any
    ) -> CertificateEndpoint:
        domain = _domain_for_certificate_request(workspace, domain_entity_id)
        try:
            return endpoints_for_domain(workspace.data_scope, domain.entity_id).get(entity_id=endpoint_entity_id)
        except CertificateEndpoint.DoesNotExist as exc:
            raise serializers.ValidationError({"detail": "The selected certificate endpoint is unavailable."}) from exc

    @extend_schema(responses={200: dict})
    def get(self, request, domain_entity_id, endpoint_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_VIEW, organization=workspace.organization)
        endpoint = self._endpoint(workspace, domain_entity_id, endpoint_entity_id)
        runs = CertificateMonitorRun.scoped.for_scope(workspace.data_scope).filter(endpoint=endpoint)[:25]
        alerts = CertificateMonitorAlert.scoped.for_scope(workspace.data_scope).filter(endpoint=endpoint)[:50]
        return Response({
            "endpoint": CertificateEndpointSerializer(endpoint).data,
            "runs": CertificateMonitorRunSerializer(runs, many=True).data,
            "alerts": CertificateMonitorAlertSerializer(alerts, many=True).data,
        })

    @extend_schema(request=None, responses={202: CertificateMonitorRunSerializer})
    def post(self, request, domain_entity_id, endpoint_entity_id, organization_entity_id=None):  # type: ignore[no-untyped-def]
        workspace = _workspace(request, organization_entity_id)
        require_permission(request.user, PermissionKey.DOMAINS_EDIT, organization=workspace.organization)
        endpoint = self._endpoint(workspace, domain_entity_id, endpoint_entity_id)
        run = enqueue_certificate_monitoring(
            scope=workspace.data_scope, endpoint=endpoint, requested_by_id=request.user.pk, trigger="manual"
        )
        return Response(CertificateMonitorRunSerializer(run).data, status=202)


@extend_schema_view(
    get=extend_schema(operation_id="msp_domain_list"),
    post=extend_schema(operation_id="msp_domain_create"),
)
class MSPDomainListCreateView(DomainListCreateView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_domain_list"),
    post=extend_schema(operation_id="organization_domain_create"),
)
class OrganizationDomainListCreateView(DomainListCreateView):
    pass


class MSPDomainReviewView(DomainReviewView):
    pass


class OrganizationDomainReviewView(DomainReviewView):
    pass


class MSPDomainMonitoringView(DomainMonitoringView):
    pass


class OrganizationDomainMonitoringView(DomainMonitoringView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="msp_certificate_endpoint_list"),
    post=extend_schema(operation_id="msp_certificate_endpoint_create"),
)
class MSPCertificateEndpointListCreateView(CertificateEndpointListCreateView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_certificate_endpoint_list"),
    post=extend_schema(operation_id="organization_certificate_endpoint_create"),
)
class OrganizationCertificateEndpointListCreateView(CertificateEndpointListCreateView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="msp_certificate_monitoring_history"),
    post=extend_schema(operation_id="msp_certificate_monitoring_scan"),
)
class MSPCertificateMonitoringView(CertificateMonitoringView):
    pass


@extend_schema_view(
    get=extend_schema(operation_id="organization_certificate_monitoring_history"),
    post=extend_schema(operation_id="organization_certificate_monitoring_scan"),
)
class OrganizationCertificateMonitoringView(CertificateMonitoringView):
    pass
