import secrets

import pytest
from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.models import AuditEvent, ContractCost, InstallationState
from apps.core.organizations import create_organization


@pytest.fixture
def installation(db):
    InstallationState.objects.get_or_create(pk=InstallationState.SINGLETON_ID)
    result = bootstrap_owner(
        tenant_name="Commercial MSP",
        owner_email="commercial-owner@example.invalid",
        owner_display_name="Commercial Owner",
        password=f"{secrets.token_urlsafe(24)}Aa7!",
    )
    TOTP.activate(result.owner, generate_totp_secret())
    return result


@pytest.fixture
def owner_client(installation):
    browser = Client()
    browser.force_login(installation.owner)
    return browser


def organization(installation, name, classification):  # type: ignore[no-untyped-def]
    return create_organization(
        tenant=installation.tenant,
        actor_id=installation.owner.id,
        name=name,
        legal_name=f"{name}, LLC",
        website="https://example.invalid",
        classifications=[classification],
    )


def create_contract(owner_client, client, provider):  # type: ignore[no-untyped-def]
    return owner_client.post(
        reverse("organization-commercial-contract-list-create", kwargs={"organization_entity_id": client.entity_id}),
        {
            "name": "Managed endpoint service",
            "provider_id": str(provider.entity_id),
            "kind": "service",
            "status": "active",
            "description": "Endpoint monitoring and response",
            "reference": "MSA-204",
            "starts_on": "2026-08-01",
            "ends_on": "2027-07-31",
            "renews_on": "2027-07-01",
            "auto_renew": True,
            "renewal_notice_days": 30,
        },
        content_type="application/json",
    )


@pytest.mark.django_db
def test_msp_contracts_are_not_an_aggregate_of_client_contracts(owner_client, installation):
    client = organization(installation, "Scoped Client", "client")
    provider = organization(installation, "Parity Provider", "vendor")
    client_contract = create_contract(owner_client, client, provider)
    msp_contract = owner_client.post(
        reverse("msp-commercial-contract-list-create"),
        {
            "name": "MSP support agreement",
            "provider_id": str(provider.entity_id),
            "kind": "support",
            "status": "active",
        },
        content_type="application/json",
    )
    assert client_contract.status_code == 201
    assert msp_contract.status_code == 201
    cost = owner_client.post(
        reverse(
            "msp-commercial-contract-cost-list-create",
            kwargs={"contract_entity_id": msp_contract.json()["id"]},
        ),
        {"label": "Internal seats", "amount": "12.50", "currency": "USD", "billing_interval": "monthly"},
        content_type="application/json",
    )
    assert cost.status_code == 201
    assert cost.json()["costs"][0]["amount"] == "12.50"
    msp_results = owner_client.get(reverse("msp-commercial-contract-list-create")).json()["results"]
    assert [item["name"] for item in msp_results] == ["MSP support agreement"]
    assert owner_client.get(
        reverse("msp-commercial-contract-detail", kwargs={"contract_entity_id": client_contract.json()["id"]})
    ).status_code == 404


@pytest.mark.django_db
def test_contract_collection_is_bounded_without_changing_cost_projection(owner_client, installation):
    client = organization(installation, "Paged Client", "client")
    provider = organization(installation, "Paged Provider", "vendor")
    collection = reverse(
        "organization-commercial-contract-list-create", kwargs={"organization_entity_id": client.entity_id}
    )
    for name in ("Alpha agreement", "Beta agreement", "Gamma agreement"):
        response = owner_client.post(
            collection,
            {"name": name, "provider_id": str(provider.entity_id), "kind": "service"},
            content_type="application/json",
        )
        assert response.status_code == 201

    first = owner_client.get(collection, {"page": 1, "page_size": 2}).json()
    assert [item["name"] for item in first["results"]] == ["Alpha agreement", "Beta agreement"]
    assert first["count"] == 3
    assert first["has_more"] is True
    assert all("costs" in item for item in first["results"])
    last = owner_client.get(collection, {"page": 2, "page_size": 2}).json()
    assert [item["name"] for item in last["results"]] == ["Gamma agreement"]
    assert last["has_more"] is False
    assert owner_client.get(collection, {"page_size": 101}).status_code == 400


@pytest.mark.django_db
def test_contract_cost_crud_and_search_never_use_financial_values(owner_client, installation):
    client = organization(installation, "Commercial Client", "client")
    provider = organization(installation, "Managed Provider", "vendor")
    sibling = organization(installation, "Sibling Client", "client")
    created = create_contract(owner_client, client, provider)
    assert created.status_code == 201
    contract_id = created.json()["id"]
    assert created.json()["provider_name"] == "Managed Provider"
    assert created.json()["costs"] == []

    cost_url = reverse(
        "organization-commercial-contract-cost-list-create",
        kwargs={"organization_entity_id": client.entity_id, "contract_entity_id": contract_id},
    )
    costed = owner_client.post(
        cost_url,
        {
            "label": "Managed devices",
            "amount": "19.50",
            "currency": "usd",
            "billing_interval": "monthly",
            "quantity": "25.000",
            "starts_on": "2026-08-01",
            "reference": "PRIVATE-RATE-19-50",
        },
        content_type="application/json",
    )
    assert costed.status_code == 201
    assert costed.json()["costs"][0]["amount"] == "19.50"
    assert costed.json()["costs"][0]["currency"] == "USD"
    cost_id = costed.json()["costs"][0]["id"]
    cost_audit = AuditEvent.objects.get(action="commercial_contract.cost_created")
    assert cost_audit.metadata == {"cost_id": cost_id}
    assert "19.50" not in str(cost_audit.metadata)
    assert "PRIVATE-RATE" not in str(cost_audit.metadata)

    list_url = reverse(
        "organization-commercial-contract-list-create", kwargs={"organization_entity_id": client.entity_id}
    )
    assert owner_client.get(list_url, {"q": "Managed Provider"}).json()["count"] == 1
    assert owner_client.get(list_url, {"q": "19.50"}).json()["count"] == 0
    assert owner_client.get(list_url, {"q": "PRIVATE-RATE"}).json()["count"] == 0

    changed = owner_client.patch(
        reverse(
            "organization-commercial-contract-cost-detail",
            kwargs={
                "organization_entity_id": client.entity_id,
                "contract_entity_id": contract_id,
                "cost_id": cost_id,
            },
        ),
        {"amount": "21.00"},
        content_type="application/json",
    )
    assert changed.status_code == 200
    assert changed.json()["costs"][0]["amount"] == "21.00"
    assert (
        owner_client.get(
            reverse(
                "organization-commercial-contract-detail",
                kwargs={"organization_entity_id": sibling.entity_id, "contract_entity_id": contract_id},
            )
        ).status_code
        == 404
    )

    contract_url = reverse(
        "organization-commercial-contract-detail",
        kwargs={"organization_entity_id": client.entity_id, "contract_entity_id": contract_id},
    )
    assert owner_client.delete(contract_url).status_code == 204
    recycled = owner_client.get(
        reverse("organization-recycle-bin", kwargs={"organization_entity_id": client.entity_id})
    ).json()["results"]
    item = next(item for item in recycled if item["record_type"] == "commercial_contract")
    assert item["label"] == "Managed endpoint service"
    assert item["cascade_count"] == 2
    restored = owner_client.post(
        reverse(
            "organization-recycle-bin-restore",
            kwargs={
                "organization_entity_id": client.entity_id,
                "record_type": "commercial_contract",
                "record_id": contract_id,
            },
        )
    )
    assert restored.status_code == 204
    assert owner_client.get(contract_url).json()["costs"][0]["amount"] == "21.00"
    removed = owner_client.delete(
        reverse(
            "organization-commercial-contract-cost-detail",
            kwargs={
                "organization_entity_id": client.entity_id,
                "contract_entity_id": contract_id,
                "cost_id": cost_id,
            },
        )
    )
    assert removed.status_code == 200
    assert removed.json()["costs"] == []


@pytest.mark.django_db
def test_cost_projection_is_omitted_and_exact_organization_grant_restores_it(owner_client, installation):
    client = organization(installation, "Visible Contract Client", "client")
    sibling = organization(installation, "Hidden Cost Client", "client")
    provider = organization(installation, "Contract Vendor", "vendor")
    contract_id = create_contract(owner_client, client, provider).json()["id"]
    owner_client.post(
        reverse(
            "organization-commercial-contract-cost-list-create",
            kwargs={"organization_entity_id": client.entity_id, "contract_entity_id": contract_id},
        ),
        {"label": "Support", "amount": "500.00", "currency": "USD", "billing_interval": "monthly"},
        content_type="application/json",
    )

    reader = User.objects.create_user(email="commercial-reader@example.invalid", display_name="Commercial Reader")
    TenantMembership.objects.create(tenant=installation.tenant, user=reader, role=BuiltInRole.READ_ONLY)
    reader_client = Client()
    reader_client.force_login(reader)
    list_url = reverse(
        "organization-commercial-contract-list-create", kwargs={"organization_entity_id": client.entity_id}
    )
    hidden = reader_client.get(list_url)
    assert hidden.status_code == 200
    assert hidden.json()["can_view_costs"] is False
    assert "costs" not in hidden.json()["results"][0]
    assert b"500.00" not in hidden.content
    assert b"Support" not in hidden.content
    assert (
        reader_client.post(
            reverse(
                "organization-commercial-contract-cost-list-create",
                kwargs={"organization_entity_id": client.entity_id, "contract_entity_id": contract_id},
            ),
            {"label": "Denied", "amount": "1.00", "currency": "USD", "billing_interval": "monthly"},
            content_type="application/json",
        ).status_code
        == 403
    )

    role = owner_client.post(
        reverse("custom-role-list-create"),
        {
            "name": "Client cost viewer",
            "description": "Exact client rates",
            "scope": "organization",
            "permissions": ["costs.view"],
        },
        content_type="application/json",
    ).json()
    owner_client.post(
        reverse("scoped-role-assignment-list-create"),
        {"user_id": str(reader.id), "role_id": role["id"], "organization_id": str(client.entity_id)},
        content_type="application/json",
    )
    visible = reader_client.get(list_url)
    assert visible.json()["results"][0]["costs"][0]["amount"] == "500.00"
    sibling_url = reverse(
        "organization-commercial-contract-list-create", kwargs={"organization_entity_id": sibling.entity_id}
    )
    assert reader_client.get(sibling_url).json()["can_view_costs"] is False

    event = ContractCost.objects.get(contract__entity_id=contract_id)
    assert event.currency == "USD"


@pytest.mark.django_db(transaction=True)
def test_postgres_rejects_commercial_scope_and_currency_forgery(owner_client, installation):
    if connection.vendor != "postgresql":
        pytest.skip("Commercial database guards require PostgreSQL")
    client = organization(installation, "Guarded Commercial Client", "client")
    provider = organization(installation, "Guarded Commercial Vendor", "vendor")
    ineligible_provider = organization(installation, "Guarded Commercial Customer", "client")
    contract_id = create_contract(owner_client, client, provider).json()["id"]
    cost_url = reverse(
        "organization-commercial-contract-cost-list-create",
        kwargs={"organization_entity_id": client.entity_id, "contract_entity_id": contract_id},
    )
    owner_client.post(
        cost_url,
        {"label": "Guarded rate", "amount": "12.00", "currency": "USD", "billing_interval": "monthly"},
        content_type="application/json",
    )
    contract = installation.tenant.commercial_contracts.get(entity_id=contract_id)
    cost = ContractCost.objects.get(contract=contract)

    with pytest.raises(DatabaseError), transaction.atomic():
        installation.tenant.commercial_contracts.filter(pk=contract.pk).update(provider=ineligible_provider)
    with pytest.raises(DatabaseError), transaction.atomic():
        ContractCost.objects.filter(pk=cost.pk).update(currency="usd")
