from django.db import migrations

FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_network_subnet() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE normalized text; old_key text; new_key text;
BEGIN
  BEGIN normalized := (NEW.cidr::cidr)::text;
  EXCEPTION WHEN invalid_text_representation THEN RAISE EXCEPTION 'network CIDR is invalid'; END;
  IF normalized <> NEW.cidr THEN RAISE EXCEPTION 'network CIDR is not canonical'; END IF;
  IF family(NEW.cidr::inet) <> NEW.address_family THEN RAISE EXCEPTION 'network address family mismatch'; END IF;
  IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
    AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND e.entity_type='network_subnet' AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network entity scope mismatch'; END IF;
  IF NEW.vrf_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_networkvrf v WHERE v.id=NEW.vrf_id
    AND v.tenant_id=NEW.tenant_id AND v.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'network VRF scope mismatch'; END IF;
  IF NEW.vlan_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_networkvlan v WHERE v.id=NEW.vlan_id
    AND v.tenant_id=NEW.tenant_id AND v.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'network VLAN scope mismatch'; END IF;
  IF NEW.location_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_location l WHERE l.id=NEW.location_id
    AND l.tenant_id=NEW.tenant_id AND l.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND l.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network location scope mismatch'; END IF;
  IF NOT NEW.use_full_range THEN
    IF family(NEW.assignable_start::inet)<>NEW.address_family OR family(NEW.assignable_end::inet)<>NEW.address_family
      OR NOT (NEW.assignable_start::inet <<= NEW.cidr::inet) OR NOT (NEW.assignable_end::inet <<= NEW.cidr::inet)
      OR NEW.assignable_start::inet > NEW.assignable_end::inet
    THEN RAISE EXCEPTION 'network assignable range is invalid'; END IF;
    IF NEW.address_family=4 AND masklen(NEW.cidr::inet)<31
      AND (NEW.assignable_start::inet=network(NEW.cidr::inet) OR NEW.assignable_end::inet=broadcast(NEW.cidr::inet))
    THEN RAISE EXCEPTION 'network assignable range includes a reserved address'; END IF;
  END IF;
  new_key := NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp') || ':' ||
    COALESCE(NEW.vrf_id::text, 'default');
  old_key := new_key;
  IF TG_OP='UPDATE' THEN
    old_key := OLD.tenant_id::text || ':' || COALESCE(OLD.organization_id::text, 'msp') || ':' ||
      COALESCE(OLD.vrf_id::text, 'default');
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(LEAST(old_key, new_key), 0));
  IF old_key<>new_key THEN PERFORM pg_advisory_xact_lock(hashtextextended(GREATEST(old_key, new_key), 0)); END IF;
  IF EXISTS (SELECT 1 FROM core_networksubnet s WHERE s.id<>NEW.id AND s.tenant_id=NEW.tenant_id
    AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id AND s.vrf_id IS NOT DISTINCT FROM NEW.vrf_id
    AND s.cidr::inet && NEW.cidr::inet)
  THEN RAISE EXCEPTION 'network overlaps an existing prefix in its routing namespace'; END IF;
  IF EXISTS (SELECT 1 FROM core_networkipaddress a WHERE a.subnet_id=NEW.id
    AND (NOT (a.address::inet <<= NEW.cidr::inet) OR family(a.address::inet)<>NEW.address_family
      OR (family(NEW.cidr::inet)=4 AND masklen(NEW.cidr::inet)<31
        AND (a.address::inet=network(NEW.cidr::inet) OR a.address::inet=broadcast(NEW.cidr::inet)))))
  THEN RAISE EXCEPTION 'network change invalidates an assigned address'; END IF;
  IF EXISTS (SELECT 1 FROM core_networkipaddress assigned
    JOIN core_networkipaddress candidate ON candidate.address::inet=assigned.address::inet
    JOIN core_networksubnet candidate_subnet ON candidate_subnet.id=candidate.subnet_id
    WHERE assigned.subnet_id=NEW.id AND candidate.subnet_id<>NEW.id AND candidate.tenant_id=NEW.tenant_id
    AND candidate.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND candidate_subnet.vrf_id IS NOT DISTINCT FROM NEW.vrf_id)
  THEN RAISE EXCEPTION 'network move creates an IP address conflict'; END IF;
  RETURN NEW;
END $$;
"""

REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION tekdocs_validate_network_subnet() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE normalized text; old_key text; new_key text;
BEGIN
  BEGIN normalized := (NEW.cidr::cidr)::text;
  EXCEPTION WHEN invalid_text_representation THEN RAISE EXCEPTION 'network subnet CIDR is invalid'; END;
  IF normalized <> NEW.cidr THEN RAISE EXCEPTION 'network subnet CIDR is not canonical'; END IF;
  IF family(NEW.cidr::inet) <> NEW.address_family THEN
    RAISE EXCEPTION 'network subnet address family mismatch';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM core_entity e WHERE e.id=NEW.entity_id
    AND e.tenant_id=NEW.tenant_id AND e.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND e.entity_type='network_subnet' AND e.archived_at IS NULL)
  THEN RAISE EXCEPTION 'network subnet entity scope mismatch'; END IF;
  IF NEW.vrf_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_networkvrf v WHERE v.id=NEW.vrf_id
    AND v.tenant_id=NEW.tenant_id AND v.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'network subnet VRF scope mismatch'; END IF;
  IF NEW.vlan_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core_networkvlan v WHERE v.id=NEW.vlan_id
    AND v.tenant_id=NEW.tenant_id AND v.organization_id IS NOT DISTINCT FROM NEW.organization_id)
  THEN RAISE EXCEPTION 'network subnet VLAN scope mismatch'; END IF;
  new_key := NEW.tenant_id::text || ':' || COALESCE(NEW.organization_id::text, 'msp') || ':' ||
    COALESCE(NEW.vrf_id::text, 'default');
  old_key := new_key;
  IF TG_OP='UPDATE' THEN
    old_key := OLD.tenant_id::text || ':' || COALESCE(OLD.organization_id::text, 'msp') || ':' ||
      COALESCE(OLD.vrf_id::text, 'default');
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(LEAST(old_key, new_key), 0));
  IF old_key<>new_key THEN
    PERFORM pg_advisory_xact_lock(hashtextextended(GREATEST(old_key, new_key), 0));
  END IF;
  IF EXISTS (SELECT 1 FROM core_networksubnet s WHERE s.id<>NEW.id
    AND s.tenant_id=NEW.tenant_id AND s.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND s.vrf_id IS NOT DISTINCT FROM NEW.vrf_id AND s.cidr::inet && NEW.cidr::inet)
  THEN RAISE EXCEPTION 'network subnet overlaps an existing prefix in its routing namespace'; END IF;
  IF EXISTS (SELECT 1 FROM core_networkipaddress a WHERE a.subnet_id=NEW.id
    AND (NOT (a.address::inet <<= NEW.cidr::inet) OR family(a.address::inet)<>NEW.address_family
      OR (family(NEW.cidr::inet)=4 AND masklen(NEW.cidr::inet)<31
        AND (a.address::inet=network(NEW.cidr::inet) OR a.address::inet=broadcast(NEW.cidr::inet)))))
  THEN RAISE EXCEPTION 'network subnet change invalidates an assigned address'; END IF;
  IF EXISTS (SELECT 1 FROM core_networkipaddress assigned
    JOIN core_networkipaddress candidate ON candidate.address::inet=assigned.address::inet
    JOIN core_networksubnet candidate_subnet ON candidate_subnet.id=candidate.subnet_id
    WHERE assigned.subnet_id=NEW.id AND candidate.subnet_id<>NEW.id AND candidate.tenant_id=NEW.tenant_id
    AND candidate.organization_id IS NOT DISTINCT FROM NEW.organization_id
    AND candidate_subnet.vrf_id IS NOT DISTINCT FROM NEW.vrf_id)
  THEN RAISE EXCEPTION 'network subnet move creates an IP address conflict'; END IF;
  RETURN NEW;
END $$;
"""


def apply_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(FORWARD_SQL)


def restore_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("core", "0074_simplify_network_records")]
    operations = [migrations.RunPython(apply_guard, restore_guard)]
