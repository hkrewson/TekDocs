import uuid

from apps.core.catalogs import create_definition, create_model, create_product
from apps.core.inventory import create_client_asset
from apps.core.organizations import create_organization


def create_network_hardware_asset(*, installation, organization, name: str):  # type: ignore[no-untyped-def]
    """Create the smallest real supplier catalog chain for an asset-backed network record."""
    suffix = uuid.uuid4().hex[:10]
    supplier = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=f"Network fixture supplier {suffix}",
        legal_name=f"Network fixture supplier {suffix}",
        website="https://example.invalid",
        classifications=["manufacturer"],
    )
    definition = create_definition(
        tenant=installation.tenant,
        organization=supplier,
        actor_id=installation.owner.id,
        name=f"Network hardware {suffix}",
        product_kind="hardware",
        schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    )
    product = create_product(
        tenant=installation.tenant,
        organization=supplier,
        actor_id=installation.owner.id,
        name=f"Network device {suffix}",
        kind="hardware",
        description="Test-only physical network asset",
    )
    specification = definition.versions.get(version=1)
    model = create_model(
        product=product,
        actor_id=installation.owner.id,
        name=f"Network model {suffix}",
        model_number=suffix.upper(),
        specification_version=specification,
        lifecycle="active",
        specifications={},
        notes="",
    )
    return create_client_asset(
        tenant=installation.tenant,
        organization=organization,
        actor_id=installation.owner.id,
        model_entity_id=model.entity_id,
        name=name,
    )
