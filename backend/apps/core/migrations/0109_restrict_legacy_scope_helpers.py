from django.db import migrations


LEGACY_SCOPE_FUNCTIONS = (
    "tekdocs_current_tenant_id()",
    "tekdocs_current_organization_id()",
    "tekdocs_current_workspace_id()",
    "tekdocs_scope_matches(uuid, uuid)",
)


FORWARD_SQL = "\n".join(
    statement
    for signature in LEGACY_SCOPE_FUNCTIONS
    for statement in (
        f"REVOKE EXECUTE ON FUNCTION {signature} FROM PUBLIC;",
        f"GRANT EXECUTE ON FUNCTION {signature} TO tekdocs_runtime;",
    )
)


REVERSE_SQL = "\n".join(
    statement
    for signature in LEGACY_SCOPE_FUNCTIONS
    for statement in (
        f"REVOKE EXECUTE ON FUNCTION {signature} FROM tekdocs_runtime;",
        f"GRANT EXECUTE ON FUNCTION {signature} TO PUBLIC;",
    )
)


class Migration(migrations.Migration):
    dependencies = [("core", "0108_principal_aware_entity_anchor_rls")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
