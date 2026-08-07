import pytest
from django.core.exceptions import ValidationError

from apps.core.models import AuditEvent, Entity, EntityLink, InstallationState, Tenant


@pytest.mark.django_db
def test_entity_link_rejects_cross_tenant_relationships():
    first = Tenant.objects.create(name="First MSP", slug="first")
    second = Tenant.objects.create(name="Second MSP", slug="second")
    source = Entity.objects.create(tenant=first, entity_type="document", display_name="Runbook")
    target = Entity.objects.create(tenant=second, entity_type="asset", display_name="Router")
    link = EntityLink(tenant=first, source=source, target=target, link_type="documents")

    with pytest.raises(ValidationError, match="Target entity"):
        link.full_clean()


@pytest.mark.django_db
def test_audit_events_are_append_only():
    event = AuditEvent.objects.create(action="system.started")
    event.metadata = {"changed": True}

    with pytest.raises(ValidationError, match="append-only"):
        event.save()
    with pytest.raises(ValidationError, match="append-only"):
        event.delete()


@pytest.mark.django_db
def test_installation_state_is_migration_created_and_not_deletable():
    state = InstallationState.objects.get(pk=InstallationState.SINGLETON_ID)

    assert state.is_bootstrapped is False
    with pytest.raises(ValidationError, match="cannot be deleted"):
        state.delete()
