"""Synthetic fixture for a newly prepared, isolated acceptance project only."""

import os
import json
import secrets
import uuid
from pathlib import Path
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from apps.accounts.bootstrap import bootstrap_owner
from apps.core.models import (
    InstallationState,
    Organization,
    Workspace,
    ContentNode,
    ClientAsset,
)
from apps.core.organizations import create_organization
from apps.core.catalogs import create_definition, create_product, create_model
from apps.core.inventory import create_client_asset
from apps.core.commercial import create_contract
from apps.core.network_addressing import create_subnet
from apps.core.network_services import create_dns_zone, create_dns_record
from apps.core.content_authoring import author_content
from apps.core.repository_storage import ensure_workspace_repository
from apps.core.document_attachments import (
    create_repository_document_attachment,
    append_repository_primary_document_file,
)
from apps.core.rls import bind_local_rls_scope, OrganizationRLSMode, RLSPrincipalMode
from apps.core.scoping import DataScope

if os.environ.get("TEKDOCS_ACCEPTANCE_FIXTURE") != "isolated-disposable":
    raise RuntimeError("Acceptance fixtures require the isolated preparation command")
assert settings.TEKDOCS_PUBLIC_URL == os.environ["TEKDOCS_ACCEPTANCE_URL"], (
    "Not the acceptance installation"
)
assert settings.EMAIL_HOST == "mailpit"
assert not ClientAsset.objects.exists() and not ContentNode.objects.exists(), (
    "Fixture data already exists; refuse duplicate seeding"
)
state = InstallationState.objects.get()
access = Path("/fixture/access.txt")
if state.is_bootstrapped:
    assert access.exists() and state.tenant.name == "Acceptance MSP"
    tenant, owner = state.tenant, state.owner
else:
    password = secrets.token_urlsafe(28)
    result = bootstrap_owner(
        tenant_name="Acceptance MSP",
        owner_email="owner@acceptance.invalid",
        owner_display_name="Acceptance Owner",
        password=password,
    )
    access.write_text(
        f"LOCAL ACCEPTANCE ONLY — {settings.TEKDOCS_PUBLIC_URL}\nEmail: owner@acceptance.invalid\nPassword: "
        + password
        + "\n\nEnroll MFA normally on first sign-in. Do not reuse this password.\n"
    )
    access.chmod(0o600)
    tenant, owner = result.tenant, result.owner


def scope(org):
    bind_local_rls_scope(
        DataScope.owner(tenant, org),
        organization_mode=OrganizationRLSMode.ORGANIZATION
        if org
        else OrganizationRLSMode.MSP_ONLY,
        actor_user_id=owner.id,
        principal_mode=RLSPrincipalMode.USER,
    )


with transaction.atomic():
    scope(None)
    orgs = [
        Organization.objects.filter(tenant=tenant, entity__display_name=name).first()
        or create_organization(
            tenant=tenant,
            actor_id=owner.id,
            name=name,
            legal_name=name,
            website="",
            classifications=[kind],
        )
        for name, kind in [
            ("Acceptance A", "client"),
            ("Acceptance B", "client"),
            ("Acceptance Supplier", "vendor"),
        ]
    ]
a, b, supplier = orgs
with transaction.atomic():
    scope(supplier)
    from apps.core.models import (
        CatalogSpecificationDefinition,
        CatalogProduct,
        CatalogModel,
    )

    definition = CatalogSpecificationDefinition.objects.filter(
        tenant=tenant, organization=supplier
    ).first() or create_definition(
        tenant=tenant,
        organization=supplier,
        actor_id=owner.id,
        name="Acceptance hardware specification",
        product_kind="hardware",
        schema={"type": "object", "additionalProperties": False, "properties": {}},
    )
    product = CatalogProduct.objects.filter(
        tenant=tenant, organization=supplier
    ).first() or create_product(
        tenant=tenant,
        organization=supplier,
        actor_id=owner.id,
        name="Acceptance Laptop",
        kind="hardware",
        description="Made-up test hardware",
    )
    model = CatalogModel.objects.filter(product=product).first() or create_model(
        product=product,
        actor_id=owner.id,
        name="Acceptance Laptop Model",
        model_number="TEST-098",
        specification_version=definition.versions.get(version=1),
        lifecycle="active",
        specifications={},
        notes="Not a real device",
    )

manifest = {
    "url": os.environ["TEKDOCS_ACCEPTANCE_URL"],
    "source_commit": os.environ["TEKDOCS_ACCEPTANCE_COMMIT"],
    "build": "local source build; not the published GHCR images",
    "workspaces": [],
}
for org, prefix in [(None, "MSP"), (a, "A"), (b, "B")]:
    with transaction.atomic():
        scope(org)
        assets = []
        for n in range(1, 31):
            asset = create_client_asset(
                tenant=tenant,
                organization=org,
                actor_id=owner.id,
                model_entity_id=model.entity_id,
                name=f"Acceptance {prefix} Laptop {n:02}",
            )
            assets.append(asset)
            create_contract(
                tenant=tenant,
                organization=org,
                actor_id=owner.id,
                values={
                    "provider_id": supplier.entity_id,
                    "name": f"Acceptance {prefix} Support {n:02}",
                    "kind": "support",
                    "description": "Disposable acceptance record",
                },
            )
            create_subnet(
                tenant=tenant,
                organization=org,
                actor_id=owner.id,
                name=f"Acceptance {prefix} Network {n:02}",
                cidr=f"10.98.{n}.0/24",
                vrf_entity_id=None,
                vlan_entity_id=None,
                description="Test documentation only; no live network",
            )
        zone = create_dns_zone(
            tenant=tenant,
            organization=org,
            actor_id=owner.id,
            name=f"{prefix.lower()}.acceptance.invalid",
            description="Local fixture; no provider connection",
        )
        create_dns_record(
            tenant=tenant,
            organization=org,
            actor_id=owner.id,
            zone_entity_id=zone.entity_id,
            owner_name=f"laptop.{prefix.lower()}.acceptance.invalid",
            record_type="A",
            value="10.98.1.10",
            ttl=300,
            priority=None,
            weight=None,
            port=None,
            ip_address_entity_id=None,
            description="Locally authored test DNS record",
        )
    workspace = Workspace.objects.get(tenant=tenant, organization=org)
    repository = ensure_workspace_repository(workspace).repository

    def author(kind, title, body, metadata):
        repository.refresh_from_db()
        with transaction.atomic():
            scope(org)
            return author_content(
                repository=repository,
                actor_id=owner.id,
                request_id=None,
                operation="create",
                content_id=uuid.uuid4(),
                base_commit=repository.accepted_commit.object_id,
                base_blob=None,
                kind=kind,
                path=None,
                title=title,
                markdown=body,
                metadata_patch=metadata,
            )

    fragment = author(
        "fragment",
        f"Acceptance {prefix} Safety Steps",
        "Disconnect power before maintenance.\n",
        {},
    )
    documents = []
    for n in range(1, 31):
        document = author(
            "document",
            f"Acceptance {prefix} Runbook {n:02}",
            f"# Acceptance {prefix} Runbook {n:02}\n\nMade-up test content, safe to edit.\n",
            {
                "includes": [
                    {
                        "id": str(fragment.content_id),
                        "mode": "live",
                        "audience": "shared",
                    }
                ]
            }
            if n == 1
            else {},
        )
        documents.append(str(document.content_id))
        with transaction.atomic():
            scope(org)
            create_repository_document_attachment(
                repository=repository,
                content_id=document.content_id,
                actor_id=owner.id,
                upload=SimpleUploadedFile(
                    f"acceptance-{prefix.lower()}-{n:02}.txt",
                    b"Harmless acceptance attachment.\n",
                    content_type="text/plain",
                ),
            )
    with transaction.atomic():
        scope(org)
        prior = None
        for n in (1, 2):
            prior = append_repository_primary_document_file(
                repository=repository,
                content_id=uuid.UUID(documents[0]),
                actor_id=owner.id,
                upload=SimpleUploadedFile(
                    f"primary-v{n}.txt",
                    f"Acceptance primary version {n}\n".encode(),
                    content_type="text/plain",
                ),
                expected_current_entity_id=prior.entity_id if prior else None,
            )
    repository.refresh_from_db()
    assert repository.accepted_commit_id == repository.indexed_commit_id
    manifest["workspaces"].append(
        {
            "name": f"Acceptance {prefix}" if org else "Acceptance MSP",
            "organization_entity_id": str(org.entity_id) if org else None,
            "repository_id": str(repository.id),
            "accepted_commit": repository.accepted_commit.object_id,
            "fragment_id": str(fragment.content_id),
            "document_ids": documents,
            "asset_01_id": str(assets[0].entity_id),
        }
    )
Path("/fixture/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("Acceptance fixture created; credentials stored privately, not printed.")
