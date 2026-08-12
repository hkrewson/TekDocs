from __future__ import annotations

import re

from drf_spectacular.openapi import AutoSchema

COLLIDING_RETRIEVE_OPERATION = re.compile(
    r"^workspaces_(?:msp|organizations)_(?:assets|contracts|licenses|networks_(?:circuits|devices|dns_records|"
    r"dns_zones|interfaces|ip_addresses|mac_addresses|racks|subnets|vlans|vrfs|wireless))_retrieve$"
)


class TekDocsAutoSchema(AutoSchema):
    """Keep generated operation IDs stable without drf-spectacular's order-based suffixes."""

    def get_operation_id(self) -> str:
        operation_id = super().get_operation_id()
        if COLLIDING_RETRIEVE_OPERATION.fullmatch(operation_id):
            return f"{operation_id}_{'detail' if self.path.rstrip('/').endswith('}') else 'list'}"
        return operation_id
