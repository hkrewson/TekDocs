"""Add safe network assignments and an explicitly legacy template fixture."""

import os
from django.conf import settings
from django.db import transaction
from apps.core.models import (
    InstallationState,
    Organization,
    ClientAsset,
    NetworkSubnet,
    NetworkIPAddress,
    Document,
)
from apps.core.rls import bind_local_rls_scope, OrganizationRLSMode, RLSPrincipalMode
from apps.core.scoping import DataScope
from apps.core.network_endpoints import create_ip_address
from apps.core.documents import create_document

if os.environ.get("TEKDOCS_ACCEPTANCE_FIXTURE") != "isolated-disposable":
    raise RuntimeError("Acceptance fixtures require the isolated preparation command")
assert settings.TEKDOCS_PUBLIC_URL == os.environ["TEKDOCS_ACCEPTANCE_URL"]
state = InstallationState.objects.get()
assert state.tenant.name == "Acceptance MSP"
for prefix in ("MSP", "A", "B"):
    org = (
        None
        if prefix == "MSP"
        else Organization.objects.get(
            tenant=state.tenant, entity__display_name=f"Acceptance {prefix}"
        )
    )
    with transaction.atomic():
        bind_local_rls_scope(
            DataScope.owner(state.tenant, org),
            organization_mode=OrganizationRLSMode.ORGANIZATION
            if org
            else OrganizationRLSMode.MSP_ONLY,
            actor_user_id=state.owner_id,
            principal_mode=RLSPrincipalMode.USER,
        )
        asset = ClientAsset.objects.get(
            tenant=state.tenant,
            organization=org,
            entity__display_name=f"Acceptance {prefix} Laptop 01",
        )
        subnet = NetworkSubnet.objects.get(
            tenant=state.tenant, organization=org, cidr="10.98.1.0/24"
        )
        if not NetworkIPAddress.objects.filter(
            tenant=state.tenant, organization=org, address="10.98.1.10"
        ).exists():
            create_ip_address(
                tenant=state.tenant,
                organization=org,
                actor_id=state.owner_id,
                address="10.98.1.10",
                subnet_entity_id=subnet.entity_id,
                interface_entity_id=None,
                status="active",
                dns_name=f"laptop.{prefix.lower()}.acceptance.invalid",
                description="Documentation-only local acceptance assignment",
                hardware_asset_entity_id=asset.entity_id,
            )
        if not Document.objects.filter(
            tenant=state.tenant,
            organization=org,
            entity__display_name=f"Acceptance {prefix} Incident Template",
        ).exists():
            create_document(
                tenant=state.tenant,
                organization=org,
                actor_id=state.owner_id,
                title=f"Acceptance {prefix} Incident Template",
                markdown="# Test incident\n\n## Symptoms\n\n## Resolution\n",
                category="procedure",
                is_template=True,
            )
print(
    "Three network-to-asset assignments and three explicitly legacy templates prepared. No live network traffic."
)
