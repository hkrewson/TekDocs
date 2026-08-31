from apps.core.capabilities import CAPABILITY_REGISTRY, CapabilityStatus
from apps.core.workspaces import CLASSIFICATION_CAPABILITIES, MSP_CAPABILITIES

EXCLUDED_CAPABILITIES = {"tickets", "accounting"}


def test_backend_registry_contains_only_supported_capabilities():
    assert all(definition.status is CapabilityStatus.SUPPORTED for definition in CAPABILITY_REGISTRY.values())


def test_excluded_capabilities_cannot_return_to_workspace_payloads():
    advertised = set(MSP_CAPABILITIES)
    for capabilities in CLASSIFICATION_CAPABILITIES.values():
        advertised.update(capabilities)

    assert advertised <= set(CAPABILITY_REGISTRY)
    assert advertised.isdisjoint(EXCLUDED_CAPABILITIES)
