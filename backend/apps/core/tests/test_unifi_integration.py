import json
import uuid
from types import SimpleNamespace

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.integration_providers import (
    ProviderObservation,
    ProviderPage,
    UniFiProvider,
    _unifi_cursor,
    unifi_api_base_url,
    validate_provider_page,
)
from apps.core.integration_secrets import decrypt_integration_secret, encrypt_integration_secret
from apps.core.integrations import enqueue_sync, process_sync_job
from apps.core.models import (
    ClientAsset,
    IntegrationConnection,
    IntegrationEntityMapping,
    NetworkDevice,
    NetworkIPAddress,
    NetworkSubnet,
    WirelessNetwork,
    workspace_for_owner,
)
from apps.core.tests.test_integrations import organization

pytest_plugins = ("apps.core.tests.test_integrations",)
UNIFI_TEST_CREDENTIAL = "private-unifi-key"  # noqa: S105


@pytest.mark.django_db
def test_unifi_connection_api_normalizes_console_url_and_encrypts_api_key(installation, monkeypatch):  # type: ignore[no-untyped-def]
    record = organization(installation, "UniFi connection client")
    browser = Client()
    browser.force_login(installation.owner)
    monkeypatch.setattr("apps.core.integrations.did_recently_authenticate", lambda _request: True)

    response = browser.post(
        reverse(
            "organization-integration-connection-list-create",
            kwargs={"organization_entity_id": record.entity_id},
        ),
        data=json.dumps(
            {
                "provider": "unifi",
                "name": "Office UniFi",
                "base_url": "https://console.example.test",
                "credentials": {"api_key": UNIFI_TEST_CREDENTIAL},
                "sync_interval_minutes": 15,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["base_url"] == "https://console.example.test/proxy/network/integration/"
    source = IntegrationConnection.objects.get(provider="unifi")
    assert UNIFI_TEST_CREDENTIAL not in json.dumps(source.secret_envelope)
    assert json.loads(
        decrypt_integration_secret(
            envelope_payload=source.secret_envelope,
            tenant_id=source.tenant_id,
            connection_id=source.id,
            generation=source.secret_generation,
        )
    ) == {"api_key": UNIFI_TEST_CREDENTIAL}


@pytest.mark.parametrize(
    ("entered", "expected"),
    (
        ("https://console.example.test", "https://console.example.test/proxy/network/integration/"),
        (
            "https://console.example.test/proxy/network/integration/",
            "https://console.example.test/proxy/network/integration/",
        ),
        ("https://controller.example.test/integration", "https://controller.example.test/integration/"),
    ),
)
def test_unifi_api_base_url_accepts_console_and_explicit_api_roots(entered, expected):  # type: ignore[no-untyped-def]
    assert unifi_api_base_url(entered) == expected


def test_unifi_provider_discovers_sites_before_bounded_resources():
    requests: list[dict[str, str]] = []

    def fetcher(**kwargs):  # type: ignore[no-untyped-def]
        requests.append(kwargs)
        return {
            "offset": 0,
            "limit": 200,
            "count": 1,
            "totalCount": 1,
            "data": [{"id": "site-1", "name": "Main", "internalReference": "default"}],
        }

    provider = UniFiProvider(fetcher=fetcher)
    connection = SimpleNamespace(base_url="https://console.example.test")
    page = provider.fetch_page(connection, secret="private-api-key", cursor="")

    assert page.observations == ()
    assert _unifi_cursor(page.next_cursor) == {"offset": 0, "resource": 0, "site": 0, "sites": ["site-1"]}
    assert requests == [
        {
            "base_url": "https://console.example.test/proxy/network/integration/",
            "relative_path": "v1/sites?offset=0&limit=200",
            "api_key": "private-api-key",
        }
    ]


def test_unifi_provider_reads_network_detail_and_keeps_only_supported_facts():
    def fetcher(**kwargs):  # type: ignore[no-untyped-def]
        path = kwargs["relative_path"]
        if path.endswith("/networks?offset=0&limit=25"):
            return {
                "offset": 0,
                "limit": 25,
                "count": 1,
                "totalCount": 1,
                "data": [
                    {
                        "id": "network-1",
                        "name": "Operations",
                        "management": "GATEWAY",
                        "enabled": True,
                        "vlanId": 42,
                    }
                ],
            }
        assert path.endswith("/networks/network-1")
        return {
            "id": "network-1",
            "name": "Operations",
            "management": "GATEWAY",
            "enabled": True,
            "vlanId": 42,
            "ipv4Configuration": {
                "hostIpAddress": "10.42.0.1",
                "prefixLength": 24,
                "dhcpConfiguration": {
                    "mode": "SERVER",
                    "dnsServerIpAddressesOverride": ["10.42.0.53", "1.1.1.1", "8.8.8.8"],
                    "ipAddressRange": {"start": "10.42.0.20", "stop": "10.42.0.200"},
                },
            },
            "firewallZone": {"name": "Private provider detail"},
        }

    provider = UniFiProvider(fetcher=fetcher)
    cursor = "eyJvZmZzZXQiOjAsInJlc291cmNlIjowLCJzaXRlIjowLCJzaXRlcyI6WyJzaXRlLTEiXX0"
    page = provider.fetch_page(
        SimpleNamespace(base_url="https://console.example.test/proxy/network/integration/"),
        secret="private-api-key",
        cursor=cursor,
    )

    assert page.observations[0].remote_type == "unifi.network"
    assert page.observations[0].safe_projection == {
        "name": "Operations",
        "site_id": "site-1",
        "management": "GATEWAY",
        "enabled": True,
        "vlan_id": 42,
        "cidr": "10.42.0.0/24",
        "subnet_mask": "255.255.255.0",
        "broadcast_ip": "10.42.0.255",
        "dhcp_mode": "SERVER",
        "dhcp_server_ip": "10.42.0.1",
        "dns_server_1": "10.42.0.53",
        "dns_server_2": "1.1.1.1",
    }
    assert page.complete_types == ("unifi.network",)
    validate_provider_page(provider, page)


@pytest.mark.parametrize(
    ("resource", "remote_type", "record", "expected"),
    (
        (
            1,
            "unifi.device",
            {
                "id": "device-1",
                "name": "Office AP",
                "model": "U7PRO",
                "macAddress": "00:11:22:33:44:55",
                "ipAddress": "10.42.0.2",
                "state": "ONLINE",
                "firmwareVersion": "7.0.1",
                "features": ["accessPoint"],
            },
            {"model": "U7PRO", "features": "accessPoint"},
        ),
        (
            2,
            "unifi.client",
            {
                "id": "client-1",
                "name": "Laptop",
                "type": "WIRELESS",
                "macAddress": "00:11:22:33:44:66",
                "ipAddress": "10.42.0.20",
                "connectedAt": "2026-09-28T12:00:00Z",
            },
            {"client_type": "WIRELESS", "ip_address": "10.42.0.20"},
        ),
        (
            3,
            "unifi.wifi",
            {
                "id": "wifi-1",
                "name": "Office",
                "type": "STANDARD",
                "enabled": True,
                "network": {"type": "SPECIFIC", "networkId": "network-1"},
                "securityConfiguration": {"type": "WPA3_PERSONAL"},
                "broadcastingFrequenciesGHz": ["5", "6"],
            },
            {"network_id": "network-1", "security": "WPA3_PERSONAL", "frequencies_ghz": "5, 6"},
        ),
    ),
)
def test_unifi_provider_projects_supported_device_client_and_wireless_facts(
    resource, remote_type, record, expected
):  # type: ignore[no-untyped-def]
    def fetcher(**_kwargs):  # type: ignore[no-untyped-def]
        return {"offset": 0, "limit": 25, "count": 1, "totalCount": 1, "data": [record]}

    provider = UniFiProvider(fetcher=fetcher)
    from apps.core.integration_providers import _encode_unifi_cursor

    cursor = _encode_unifi_cursor({"sites": ["site-1"], "resource": resource, "site": 0, "offset": 0})
    page = provider.fetch_page(SimpleNamespace(base_url="https://console.example.test"), secret="key", cursor=cursor)

    observation = page.observations[0]
    assert observation.remote_type == remote_type
    assert all(observation.safe_projection[key] == value for key, value in expected.items())
    assert all(not isinstance(value, dict | list) for value in observation.safe_projection.values())
    validate_provider_page(provider, page)


@pytest.mark.django_db
def test_unifi_sync_creates_supported_network_asset_ip_and_wireless_records(installation):  # type: ignore[no-untyped-def]
    client = organization(installation, "UniFi projection client")
    connection_id = uuid.uuid4()
    source = IntegrationConnection.objects.create(
        id=connection_id,
        tenant=installation.tenant,
        workspace=workspace_for_owner(tenant=installation.tenant, organization=client),
        organization=client,
        provider="unifi",
        name="Office UniFi",
        base_url="https://console.example.test/proxy/network/integration/",
        configuration={},
        secret_envelope=encrypt_integration_secret(
            secret=json.dumps({"api_key": UNIFI_TEST_CREDENTIAL}).encode(),
            tenant_id=installation.tenant.id,
            connection_id=connection_id,
            generation=1,
        ),
        created_by=installation.owner,
    )
    job = enqueue_sync(connection=source, trigger="manual", requested_by_id=installation.owner.id)

    class ProjectionAdapter:
        key = UniFiProvider.key
        label = UniFiProvider.label
        contract = UniFiProvider.contract

        def fetch_page(self, _connection, *, secret, cursor):  # type: ignore[no-untyped-def]
            assert secret == UNIFI_TEST_CREDENTIAL
            assert cursor == ""
            return ProviderPage(
                (
                    ProviderObservation(
                        "unifi.network",
                        "network-1",
                        "1" * 64,
                        {
                            "name": "Operations",
                            "site_id": "site-1",
                            "cidr": "10.42.0.0/24",
                            "vlan_id": 42,
                            "dhcp_server_ip": "10.42.0.1",
                            "dns_server_1": "10.42.0.53",
                            "dns_server_2": "1.1.1.1",
                        },
                    ),
                    ProviderObservation(
                        "unifi.device",
                        "device-1",
                        "2" * 64,
                        {
                            "name": "Office AP",
                            "site_id": "site-1",
                            "model": "U7PRO",
                            "serial": "AP-SERIAL-1",
                            "state": "ONLINE",
                            "features": "accessPoint",
                        },
                    ),
                    ProviderObservation(
                        "unifi.client",
                        "client-1",
                        "3" * 64,
                        {
                            "name": "Guest phone",
                            "site_id": "site-1",
                            "client_type": "WIRELESS",
                            "mac_address": "00:11:22:33:44:66",
                            "ip_address": "10.42.0.20",
                        },
                    ),
                    ProviderObservation(
                        "unifi.wifi",
                        "wifi-1",
                        "4" * 64,
                        {
                            "name": "Office",
                            "site_id": "site-1",
                            "enabled": True,
                            "network_id": "network-1",
                            "security": "WPA3_PERSONAL",
                        },
                    ),
                ),
                "",
                ("unifi.network", "unifi.device", "unifi.client", "unifi.wifi"),
            )

    completed = process_sync_job(job_id=job.id, adapter=ProjectionAdapter())

    assert completed.state == "succeeded"
    network = NetworkSubnet.objects.get(organization=client)
    assert (network.cidr, network.vlan_number, network.dhcp_server) == ("10.42.0.0/24", 42, "10.42.0.1")
    assert (network.primary_dns, network.secondary_dns) == ("10.42.0.53", "1.1.1.1")
    device = NetworkDevice.objects.select_related("hardware_asset__hardware", "hardware_asset__model").get(
        organization=client
    )
    assert device.hardware_asset.entity.display_name == "Office AP"
    assert device.hardware_asset.model.model_number == "U7PRO"
    assert device.hardware_asset.hardware.serial_number == "AP-SERIAL-1"
    address = NetworkIPAddress.objects.get(organization=client)
    assert (address.address, address.status, address.hardware_asset_id) == ("10.42.0.20", "dhcp", None)
    wireless = WirelessNetwork.objects.get(organization=client)
    assert (wireless.ssid, wireless.security, wireless.subnet_id) == ("Office", "wpa3_personal", network.id)
    assert ClientAsset.objects.filter(organization=client).count() == 1
    assert IntegrationEntityMapping.objects.filter(connection=source).count() == 4

    repeated = enqueue_sync(
        connection=source,
        trigger="manual",
        requested_by_id=installation.owner.id,
        idempotency_key="repeat-unifi-projection",
    )
    process_sync_job(job_id=repeated.id, adapter=ProjectionAdapter())
    assert NetworkSubnet.objects.filter(organization=client).count() == 1
    assert NetworkDevice.objects.filter(organization=client).count() == 1
    assert NetworkIPAddress.objects.filter(organization=client).count() == 1
    assert WirelessNetwork.objects.filter(organization=client).count() == 1
    assert ClientAsset.objects.filter(organization=client).count() == 1
    assert IntegrationEntityMapping.objects.filter(connection=source).count() == 4
