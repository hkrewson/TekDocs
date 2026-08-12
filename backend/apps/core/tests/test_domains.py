import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.core.domains import DomainInput, create_domain, normalize_domain_name
from apps.core.models import InstallationState
from apps.core.organizations import create_organization
from apps.core.workspaces import resolve_organization_workspace


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Domain MSP",
        owner_email="domain-owner@example.invalid",
        owner_display_name="Domain Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.mark.django_db
def test_registered_domain_is_normalized_and_exact_workspace_scoped(installation):
    first = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="First Client",
        legal_name="First Client LLC",
        website="",
        classifications=["client"],
    )
    sibling = create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name="Sibling Client",
        legal_name="Sibling Client LLC",
        website="",
        classifications=["client"],
    )
    workspace = resolve_organization_workspace(installation.owner, entity_id=first.entity_id)
    domain = create_domain(
        workspace=workspace,
        actor_id=installation.owner.id,
        value=DomainInput(name="EXAMPLE.COM.", renewal_mode="auto", status="active"),
    )
    assert domain.ascii_name == "example.com"
    assert normalize_domain_name("bücher.example") == "xn--bcher-kva.example"

    browser = Client()
    browser.force_login(installation.owner)
    first_url = reverse("organization-domain-list-create", kwargs={"organization_entity_id": first.entity_id})
    sibling_url = reverse("organization-domain-list-create", kwargs={"organization_entity_id": sibling.entity_id})
    assert browser.get(first_url).json()[0]["id"] == str(domain.entity_id)
    assert browser.get(sibling_url).json() == []
