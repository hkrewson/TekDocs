# ruff: noqa: E501, I001

from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_network_device() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
    AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND e.entity_type='network_device' AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network device entity scope mismatch'; END IF;
  IF TG_OP='INSERT' AND NEW.hardware_asset_id IS NULL
  THEN RAISE EXCEPTION 'new network device requires hardware asset'; END IF;
  IF TG_OP='INSERT' AND NEW.legacy_unbacked
  THEN RAISE EXCEPTION 'legacy network marker cannot be inserted'; END IF;
  IF TG_OP='UPDATE' AND NEW.legacy_unbacked AND NOT OLD.legacy_unbacked
  THEN RAISE EXCEPTION 'legacy network marker cannot be enabled'; END IF;
  IF NEW.hardware_asset_id IS NULL AND NOT NEW.legacy_unbacked
  THEN RAISE EXCEPTION 'network device requires hardware asset'; END IF;
  IF NEW.hardware_asset_id IS NOT NULL AND NEW.legacy_unbacked
  THEN RAISE EXCEPTION 'asset-backed network device cannot remain legacy'; END IF;
  IF NEW.hardware_asset_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_clientasset a JOIN core_catalogproduct p ON p.id=a.product_id
    JOIN core_entity e ON e.id=a.entity_id
    WHERE a.id=NEW.hardware_asset_id AND a.tenant_id=NEW.tenant_id
      AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND a.archived_at IS NULL AND e.archived_at IS NULL AND p.kind='hardware')
  THEN RAISE EXCEPTION 'network device hardware asset scope mismatch'; END IF;
  IF NEW.site_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_site s WHERE s.id=NEW.site_id
    AND s.tenant_id=NEW.tenant_id AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND s.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network device site scope mismatch'; END IF;
  IF NEW.location_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_location l
    WHERE l.id=NEW.location_id AND l.site_id=NEW.site_id AND l.tenant_id=NEW.tenant_id
      AND l.organization_id IS NOT DISTINCT FROM NEW.organization_id AND l.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network device location scope mismatch'; END IF;
  IF NEW.rack_id IS NOT NULL THEN
    PERFORM pg_advisory_xact_lock(hashtextextended(NEW.rack_id::text, 0));
    IF NOT EXISTS (SELECT 1 FROM core_networkrack r WHERE r.id=NEW.rack_id
      AND r.tenant_id=NEW.tenant_id AND r.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND r.site_id=NEW.site_id AND r.location_id IS NOT DISTINCT FROM NEW.location_id
      AND NEW.rack_unit + NEW.rack_units - 1 <= r.unit_count)
    THEN RAISE EXCEPTION 'network device rack placement mismatch'; END IF;
    IF EXISTS (SELECT 1 FROM core_networkdevice d WHERE d.rack_id=NEW.rack_id AND d.id<>NEW.id
      AND int4range(d.rack_unit, d.rack_unit + d.rack_units, '[)')
        && int4range(NEW.rack_unit, NEW.rack_unit + NEW.rack_units, '[)'))
    THEN RAISE EXCEPTION 'network device rack placement overlaps'; END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_validate_network_mac() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.address !~ '^[0-9a-f]{2}(:[0-9a-f]{2}){5}$'
  THEN RAISE EXCEPTION 'network MAC address is not canonical'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
    AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND e.entity_type='network_mac_address' AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network MAC entity scope mismatch'; END IF;
  IF NEW.interface_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_networkinterface i JOIN core_entity e ON e.id=i.entity_id
    WHERE i.id=NEW.interface_id AND i.tenant_id=NEW.tenant_id
    AND i.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network MAC interface scope mismatch'; END IF;
  IF NEW.hardware_asset_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_clientasset a JOIN core_catalogproduct p ON p.id=a.product_id
    JOIN core_entity e ON e.id=a.entity_id WHERE a.id=NEW.hardware_asset_id
      AND a.tenant_id=NEW.tenant_id AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND a.archived_at IS NULL AND e.archived_at IS NULL AND p.kind='hardware')
  THEN RAISE EXCEPTION 'network MAC hardware asset scope mismatch'; END IF;
  IF NEW.interface_id IS NOT NULL AND NEW.hardware_asset_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM core_networkinterface i JOIN core_networkdevice d ON d.id=i.device_id
    WHERE i.id=NEW.interface_id AND d.hardware_asset_id IS NOT NULL
      AND d.hardware_asset_id<>NEW.hardware_asset_id)
  THEN RAISE EXCEPTION 'network MAC legacy interface and asset disagree'; END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION tekdocs_validate_network_ip() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE normalized text; subnet_cidr cidr; subnet_vrf uuid; namespace_key text;
BEGIN
  BEGIN normalized := host(NEW.address::inet);
  EXCEPTION WHEN invalid_text_representation THEN RAISE EXCEPTION 'network IP address is invalid'; END;
  IF normalized <> NEW.address THEN RAISE EXCEPTION 'network IP address is not canonical'; END IF;
  IF family(NEW.address::inet) <> NEW.address_family THEN RAISE EXCEPTION 'network IP address family mismatch'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
    AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND e.entity_type='network_ip_address' AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network IP entity scope mismatch'; END IF;
  SELECT s.cidr::cidr, s.vrf_id INTO subnet_cidr, subnet_vrf FROM core_networksubnet s
    JOIN core_entity e ON e.id=s.entity_id WHERE s.id=NEW.subnet_id
    AND s.tenant_id=NEW.tenant_id AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND e.archived_at IS NULL;
  IF subnet_cidr IS NULL THEN RAISE EXCEPTION 'network IP subnet scope mismatch'; END IF;
  IF NOT (NEW.address::inet <<= subnet_cidr::inet) THEN RAISE EXCEPTION 'network IP address is outside its subnet'; END IF;
  IF family(subnet_cidr::inet)=4 AND masklen(subnet_cidr::inet)<31
    AND (NEW.address::inet=network(subnet_cidr::inet) OR NEW.address::inet=broadcast(subnet_cidr::inet))
  THEN RAISE EXCEPTION 'network or broadcast address cannot be assigned'; END IF;
  IF NEW.interface_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_networkinterface i JOIN core_entity e ON e.id=i.entity_id
    WHERE i.id=NEW.interface_id AND i.tenant_id=NEW.tenant_id
    AND i.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network IP interface scope mismatch'; END IF;
  IF NEW.hardware_asset_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_clientasset a JOIN core_catalogproduct p ON p.id=a.product_id
    JOIN core_entity e ON e.id=a.entity_id WHERE a.id=NEW.hardware_asset_id
      AND a.tenant_id=NEW.tenant_id AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND a.archived_at IS NULL AND e.archived_at IS NULL AND p.kind='hardware')
  THEN RAISE EXCEPTION 'network IP hardware asset scope mismatch'; END IF;
  IF NEW.interface_id IS NOT NULL AND NEW.hardware_asset_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM core_networkinterface i JOIN core_networkdevice d ON d.id=i.device_id
    WHERE i.id=NEW.interface_id AND d.hardware_asset_id IS NOT NULL
      AND d.hardware_asset_id<>NEW.hardware_asset_id)
  THEN RAISE EXCEPTION 'network IP legacy interface and asset disagree'; END IF;
  namespace_key := NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp') || ':' || COALESCE(subnet_vrf::text, 'default');
  PERFORM pg_advisory_xact_lock(hashtextextended(namespace_key, 0));
  IF EXISTS (SELECT 1 FROM core_networkipaddress a
    JOIN core_networksubnet existing_subnet ON existing_subnet.id=a.subnet_id
    WHERE a.id<>NEW.id AND a.tenant_id=NEW.tenant_id
    AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND existing_subnet.vrf_id IS NOT DISTINCT FROM subnet_vrf AND a.address::inet=NEW.address::inet)
  THEN RAISE EXCEPTION 'network IP address conflicts in its routing namespace'; END IF;
  RETURN NEW;
END $$;
"""


REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_network_device() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
    AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND e.entity_type='network_device' AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network device entity scope mismatch'; END IF;
  IF NEW.hardware_asset_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_clientasset a JOIN core_catalogproduct p ON p.id=a.product_id
    WHERE a.id=NEW.hardware_asset_id AND a.tenant_id=NEW.tenant_id
      AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND a.archived_at IS NULL AND p.kind='hardware')
  THEN RAISE EXCEPTION 'network device hardware asset scope mismatch'; END IF;
  IF NEW.site_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_site s WHERE s.id=NEW.site_id
    AND s.tenant_id=NEW.tenant_id AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND s.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network device site scope mismatch'; END IF;
  IF NEW.location_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_location l
    WHERE l.id=NEW.location_id AND l.site_id=NEW.site_id AND l.tenant_id=NEW.tenant_id
      AND l.organization_id IS NOT DISTINCT FROM NEW.organization_id AND l.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network device location scope mismatch'; END IF;
  IF NEW.rack_id IS NOT NULL THEN
    PERFORM pg_advisory_xact_lock(hashtextextended(NEW.rack_id::text, 0));
    IF NOT EXISTS (SELECT 1 FROM core_networkrack r WHERE r.id=NEW.rack_id
      AND r.tenant_id=NEW.tenant_id AND r.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND r.site_id=NEW.site_id AND r.location_id IS NOT DISTINCT FROM NEW.location_id
      AND NEW.rack_unit + NEW.rack_units - 1 <= r.unit_count)
    THEN RAISE EXCEPTION 'network device rack placement mismatch'; END IF;
    IF EXISTS (SELECT 1 FROM core_networkdevice d WHERE d.rack_id=NEW.rack_id AND d.id<>NEW.id
      AND int4range(d.rack_unit, d.rack_unit + d.rack_units, '[)')
        && int4range(NEW.rack_unit, NEW.rack_unit + NEW.rack_units, '[)'))
    THEN RAISE EXCEPTION 'network device rack placement overlaps'; END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION tekdocs_validate_network_mac() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.address !~ '^[0-9a-f]{2}(:[0-9a-f]{2}){5}$' THEN RAISE EXCEPTION 'network MAC address is not canonical'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id AND e.tenant_id=NEW.tenant_id
    AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.entity_type='network_mac_address' AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network MAC entity scope mismatch'; END IF;
  IF NEW.interface_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_networkinterface i JOIN core_entity e ON e.id=i.entity_id
    WHERE i.id=NEW.interface_id AND i.tenant_id=NEW.tenant_id
    AND i.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network MAC interface scope mismatch'; END IF;
  RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION tekdocs_validate_network_ip() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE normalized text; subnet_cidr cidr; subnet_vrf uuid; namespace_key text;
BEGIN
  BEGIN normalized := host(NEW.address::inet); EXCEPTION WHEN invalid_text_representation THEN RAISE EXCEPTION 'network IP address is invalid'; END;
  IF normalized <> NEW.address THEN RAISE EXCEPTION 'network IP address is not canonical'; END IF;
  IF family(NEW.address::inet) <> NEW.address_family THEN RAISE EXCEPTION 'network IP address family mismatch'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
    AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND e.entity_type='network_ip_address' AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network IP entity scope mismatch'; END IF;
  SELECT s.cidr::cidr, s.vrf_id INTO subnet_cidr, subnet_vrf FROM core_networksubnet s
    JOIN core_entity e ON e.id=s.entity_id WHERE s.id=NEW.subnet_id
    AND s.tenant_id=NEW.tenant_id AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND e.archived_at IS NULL;
  IF subnet_cidr IS NULL THEN RAISE EXCEPTION 'network IP subnet scope mismatch'; END IF;
  IF NOT (NEW.address::inet <<= subnet_cidr::inet) THEN RAISE EXCEPTION 'network IP address is outside its subnet'; END IF;
  IF family(subnet_cidr::inet)=4 AND masklen(subnet_cidr::inet)<31
    AND (NEW.address::inet=network(subnet_cidr::inet) OR NEW.address::inet=broadcast(subnet_cidr::inet))
  THEN RAISE EXCEPTION 'network or broadcast address cannot be assigned'; END IF;
  IF NEW.interface_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM core_networkinterface i JOIN core_entity e ON e.id=i.entity_id
    WHERE i.id=NEW.interface_id AND i.tenant_id=NEW.tenant_id
    AND i.organization_id IS NOT DISTINCT FROM NEW.organization_id AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network IP interface scope mismatch'; END IF;
  namespace_key := NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp') || ':' || COALESCE(subnet_vrf::text, 'default');
  PERFORM pg_advisory_xact_lock(hashtextextended(namespace_key, 0));
  IF EXISTS (SELECT 1 FROM core_networkipaddress a JOIN core_networksubnet s ON s.id=a.subnet_id
    WHERE a.id<>NEW.id AND a.tenant_id=NEW.tenant_id AND a.organization_id IS NOT DISTINCT FROM NEW.organization_id
      AND s.vrf_id IS NOT DISTINCT FROM subnet_vrf AND a.address::inet=NEW.address::inet)
  THEN RAISE EXCEPTION 'network IP address conflicts in its routing namespace'; END IF;
  RETURN NEW;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0061_networkdevice_legacy_unbacked_and_more")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
