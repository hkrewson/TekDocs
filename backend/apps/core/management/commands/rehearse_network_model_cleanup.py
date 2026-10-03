from __future__ import annotations

import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q

from apps.core.models import (
    InstallationState,
    NetworkCircuit,
    NetworkCircuitHandoff,
    NetworkDevice,
    NetworkInterface,
    NetworkIPAddress,
    NetworkMACAddress,
    NetworkRack,
    NetworkSubnet,
    NetworkVLAN,
    NetworkVRF,
    Organization,
)
from apps.core.rls import OrganizationRLSMode, RLSPrincipalMode, bind_local_rls_scope
from apps.core.scoping import DataScope


class Command(BaseCommand):
    help = "Report and optionally backfill records for the corrected Networks model."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--organization", required=True, help="Organization entity UUID")
        parser.add_argument("--apply", action="store_true", help="Apply lossless projection backfills")

    @transaction.atomic
    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        installation = InstallationState.objects.select_related("tenant").get(
            pk=InstallationState.SINGLETON_ID
        )
        if connection.vendor == "postgresql":
            bind_local_rls_scope(
                DataScope.tenant(installation.tenant),
                organization_mode=OrganizationRLSMode.MSP_ONLY,
                actor_user_id=None,
                principal_mode=RLSPrincipalMode.SYSTEM,
            )
        try:
            organization_id = UUID(options["organization"])
            organization = Organization.objects.get(tenant=installation.tenant, entity_id=organization_id)
        except (ValueError, Organization.DoesNotExist) as exc:
            raise CommandError("The organization workspace is unavailable.") from exc

        if connection.vendor == "postgresql":
            bind_local_rls_scope(
                DataScope.organization(installation.tenant, organization),
                organization_mode=OrganizationRLSMode.ORGANIZATION,
                actor_user_id=None,
                principal_mode=RLSPrincipalMode.SYSTEM,
            )

        scoped = {"tenant": organization.tenant, "organization": organization}
        subnets = NetworkSubnet.objects.filter(**scoped).select_related("vlan")
        devices = NetworkDevice.objects.filter(**scoped).select_related("rack")
        addresses = NetworkIPAddress.objects.filter(**scoped).select_related("interface__device")
        mac_addresses = NetworkMACAddress.objects.filter(**scoped).select_related("interface__device")
        rack_backfills = devices.filter(rack__isnull=False).filter(
            Q(source_rack_name="") | Q(source_rack_position__isnull=True) | Q(source_rack_units__isnull=True)
        )
        ip_asset_backfills = addresses.filter(
            interface__isnull=False,
            interface__device__hardware_asset__isnull=False,
            hardware_asset__isnull=True,
        )
        mac_asset_backfills = mac_addresses.filter(
            interface__isnull=False,
            interface__device__hardware_asset__isnull=False,
            hardware_asset__isnull=True,
        )
        blockers: list[dict[str, str]] = []
        for subnet in subnets.filter(vlan__isnull=False):
            vlan = subnet.vlan
            if vlan is not None and subnet.vlan_number not in (None, vlan.vlan_id):
                blockers.append({"record": str(subnet.entity_id), "reason": "CIDR VLAN values disagree"})
        for ip_address in addresses.filter(interface__isnull=False, hardware_asset__isnull=False):
            interface = ip_address.interface
            asset_id = interface.device.hardware_asset_id if interface is not None else None
            if asset_id is not None and asset_id != ip_address.hardware_asset_id:
                blockers.append(
                    {
                        "record": str(ip_address.entity_id),
                        "reason": "IP interface and asset assignments disagree",
                    }
                )
        for mac_address in mac_addresses.filter(interface__isnull=False, hardware_asset__isnull=False):
            interface = mac_address.interface
            asset_id = interface.device.hardware_asset_id if interface is not None else None
            if asset_id is not None and asset_id != mac_address.hardware_asset_id:
                blockers.append(
                    {
                        "record": str(mac_address.entity_id),
                        "reason": "MAC interface and asset assignments disagree",
                    }
                )

        report = {
            "workspace": str(organization.entity_id),
            "supported": {
                "networks": subnets.count(),
                "devices": devices.count(),
                "ip_addresses": addresses.count(),
                "mac_addresses": mac_addresses.count(),
            },
            "legacy": {
                "racks": NetworkRack.objects.filter(**scoped).count(),
                "vlans": NetworkVLAN.objects.filter(**scoped).count(),
                "vrfs": NetworkVRF.objects.filter(**scoped).count(),
                "interfaces": NetworkInterface.objects.filter(**scoped).count(),
                "circuits": NetworkCircuit.objects.filter(**scoped).count(),
                "circuit_handoffs": NetworkCircuitHandoff.objects.filter(**scoped).count(),
                "unbacked_devices": devices.filter(legacy_unbacked=True).count(),
            },
            "legacy_relationships": {
                "subnets_to_vlans": subnets.filter(vlan__isnull=False).count(),
                "subnets_to_vrfs": subnets.filter(vrf__isnull=False).count(),
                "devices_to_racks": devices.filter(rack__isnull=False).count(),
                "ip_addresses_to_interfaces": addresses.filter(interface__isnull=False).count(),
                "mac_addresses_to_interfaces": mac_addresses.filter(interface__isnull=False).count(),
                "handoffs_to_interfaces": NetworkCircuitHandoff.objects.filter(
                    **scoped, interface__isnull=False
                ).count(),
            },
            "planned_backfills": {
                "network_vlan_numbers": subnets.filter(vlan__isnull=False, vlan_number__isnull=True).count(),
                "device_rack_facts": rack_backfills.count(),
                "ip_asset_assignments": ip_asset_backfills.count(),
                "mac_asset_assignments": mac_asset_backfills.count(),
            },
            "unresolved_relationships": {
                "ip_asset_assignments": addresses.filter(
                    interface__isnull=False,
                    interface__device__hardware_asset__isnull=True,
                    hardware_asset__isnull=True,
                ).count(),
                "mac_asset_assignments": mac_addresses.filter(
                    interface__isnull=False,
                    interface__device__hardware_asset__isnull=True,
                    hardware_asset__isnull=True,
                ).count(),
            },
            "disposition": {
                "legacy_records": "retained",
                "destructive_removal": "requires_separate_deprecation_and_operator_approved_migration",
            },
            "blockers": blockers,
            "applied": False,
        }
        if options["apply"]:
            if blockers:
                raise CommandError(json.dumps(report, sort_keys=True))
            for subnet in subnets.filter(vlan__isnull=False):
                vlan = subnet.vlan
                if vlan is not None:
                    subnet.vlan_number = vlan.vlan_id
                    subnet.save(update_fields=("vlan_number", "updated_at"))
            for device in devices.filter(rack__isnull=False):
                rack = device.rack
                if rack is None:
                    continue
                device.source_rack_name = device.source_rack_name or rack.entity.display_name
                device.source_rack_position = device.source_rack_position or device.rack_unit
                device.source_rack_units = device.source_rack_units or device.rack_units
                device.save(
                    update_fields=("source_rack_name", "source_rack_position", "source_rack_units", "updated_at")
                )
            for ip_address in addresses.filter(interface__isnull=False, hardware_asset__isnull=True):
                interface = ip_address.interface
                asset_id = interface.device.hardware_asset_id if interface is not None else None
                if asset_id is not None:
                    ip_address.hardware_asset_id = asset_id
                    ip_address.save(update_fields=("hardware_asset", "updated_at"))
            for mac_address in mac_addresses.filter(interface__isnull=False, hardware_asset__isnull=True):
                interface = mac_address.interface
                asset_id = interface.device.hardware_asset_id if interface is not None else None
                if asset_id is not None:
                    mac_address.hardware_asset_id = asset_id
                    mac_address.save(update_fields=("hardware_asset", "updated_at"))
            report["applied"] = True
        self.stdout.write(json.dumps(report, sort_keys=True))
