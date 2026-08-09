RUNTIME_ROLE = "tekdocs_runtime"

ORGANIZATION_SCOPED_TABLES = (
    "core_entity",
    "core_site",
    "core_location",
    "core_customfielddefinition",
    "core_personassociation",
    "core_document",
    "core_block",
    "core_blockrevision",
    "core_documentplacement",
    "core_documentationlistingreference",
)

TENANT_SCOPED_TABLES = (
    "core_organization",
    "core_organizationclassification",
    "core_customfielddefinitionversion",
    "core_person",
    "core_entitylink",
    "core_auditevent",
)

RLS_TABLES = ORGANIZATION_SCOPED_TABLES + TENANT_SCOPED_TABLES
