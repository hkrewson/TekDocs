from __future__ import annotations

import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import (
    NetworkCircuit,
    NetworkCircuitHandoff,
    NetworkDevice,
    NetworkInterface,
    NetworkIPAddress,
    NetworkRack,
    NetworkSubnet,
    NetworkVLAN,
    NetworkVRF,
    Organization,
)


class Command(BaseCommand):
    help = "Report and optionally backfill records for the corrected Networks model."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--organization", required=True, help="Organization entity UUID")
        parser.add_argument("--apply", action="store_true", help="Apply lossless projection backfills")

    @transaction.atomic
    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        try:
            organization_id = UUID(options["organization"])
            organization = Organization.objects.get(entity_id=organization_id)
        except (ValueError, Organization.DoesNotExist) as exc:
            raise CommandError("The organization workspace is unavailable.") from exc

        scoped = {"tenant": organization.tenant, "organization": organization}
        subnets = NetworkSubnet.objects.filter(**scoped).select_related("vlan")
        devices = NetworkDevice.objects.filter(**scoped).select_related("rack")
        addresses = NetworkIPAddress.objects.filter(**scoped).select_related("interface__device")
        blockers: list[dict[str, str]] = []
        for subnet in subnets.filter(vlan__isnull=False):
            vlan = subnet.vlan
            if vlan is not None and subnet.vlan_number not in (None, vlan.vlan_id):
                blockers.append({"record": str(subnet.entity_id), "reason": "CIDR VLAN values disagree"})
        for address in addresses.filter(interface__isnull=False, hardware_asset__isnull=False):
            interface = address.interface
            asset_id = interface.device.hardware_asset_id if interface is not None else None
            if asset_id is not None and asset_id != address.hardware_asset_id:
                blockers.append(
                    {"record": str(address.entity_id), "reason": "IP interface and asset assignments disagree"}
                )

        report = {
            "workspace": str(organization.entity_id),
            "supported": {
                "networks": subnets.count(),
                "devices": devices.count(),
                "ip_addresses": addresses.count(),
            },
            "legacy": {
                "racks": NetworkRack.objects.filter(**scoped).count(),
                "vlans": NetworkVLAN.objects.filter(**scoped).count(),
                "vrfs": NetworkVRF.objects.filter(**scoped).count(),
                "interfaces": NetworkInterface.objects.filter(**scoped).count(),
                "circuits": NetworkCircuit.objects.filter(**scoped).count(),
                "circuit_handoffs": NetworkCircuitHandoff.objects.filter(**scoped).count(),
            },
            "planned_backfills": {
                "network_vlan_numbers": subnets.filter(vlan__isnull=False).count(),
                "device_rack_facts": devices.filter(rack__isnull=False).count(),
                "ip_asset_assignments": addresses.filter(interface__isnull=False).count(),
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
            for address in addresses.filter(interface__isnull=False, hardware_asset__isnull=True):
                interface = address.interface
                asset_id = interface.device.hardware_asset_id if interface is not None else None
                if asset_id is not None:
                    address.hardware_asset_id = asset_id
                    address.save(update_fields=("hardware_asset", "updated_at"))
            report["applied"] = True
        self.stdout.write(json.dumps(report, sort_keys=True))
