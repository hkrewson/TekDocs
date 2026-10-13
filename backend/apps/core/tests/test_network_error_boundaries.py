"""Keep public validation guidance distinct from database diagnostics."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.core import (
    netbox_reconciliation_views,
    network_addressing_views,
    network_circuit_views,
    network_endpoint_views,
    network_service_views,
)
from apps.core.netbox_reconciliation import NetBoxReferenceError
from apps.core.network_addressing import NetworkAddressingError
from apps.core.network_circuits import NetworkCircuitError
from apps.core.network_endpoints import NetworkEndpointError
from apps.core.network_services import NetworkServiceError


@pytest.mark.parametrize("view,domain_error,safe_message", (
    (netbox_reconciliation_views, NetBoxReferenceError,
     "That NetBox identity conflicts with another record in this Workspace."),
    (network_addressing_views, NetworkAddressingError,
     "That value conflicts with an existing network record in this Workspace."),
    (network_circuit_views, NetworkCircuitError,
     "That circuit or handoff conflicts with an existing record in this Workspace."),
    (network_endpoint_views, NetworkEndpointError,
     "That value conflicts with an existing network record in this Workspace."),
    (network_service_views, NetworkServiceError,
     "That value conflicts with an existing record in this Workspace."),
))
@pytest.mark.parametrize("kind", ("database", "validation", "domain"))
def test_network_error_translation_does_not_expose_database_diagnostics(view, domain_error, safe_message, kind):
    diagnostic = "synthetic private row and database constraint"
    public_message = "Choose a valid record in this Workspace."
    if kind == "database":
        error = IntegrityError(diagnostic)
        expected = safe_message
    elif kind == "validation":
        error = ValidationError(public_message)
        expected = public_message
    else:
        error = domain_error(public_message)
        expected = public_message
    translated = view._error(error)
    assert translated.status_code == 400
    assert diagnostic not in str(translated.detail)
    assert str(translated.detail["detail"]) == expected
