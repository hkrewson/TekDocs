# ADR 0010: Versioned custom fields

- Status: Accepted
- Date: 2026-08-08

## Decision

Use stable `CustomFieldDefinition` records with immutable, sequential `CustomFieldDefinitionVersion` children. A definition is owned either by the MSP or exactly one organization and targets one Entity type. Its normalized key, target type, tenant, and organization scope are identity properties; changing one requires a new definition rather than reinterpreting existing data.

Each version stores the user-facing label and help text, required marker, bounded field type, display order, and a server-generated JSON Schema. TekDocs accepts text, integer, number, boolean, date, URL, email, choice, and multi-choice definitions in `0.1.7`. The browser supplies ordinary configuration controls, not arbitrary schemas. The server generates and validates Draft 2020-12 schemas with a maintained implementation. Custom fields are not a secret-storage path.

Store values in the existing `Entity.custom_fields` JSON object rather than creating an EAV-only value table. Each definition-keyed envelope contains the immutable definition-version identifier, sequential version number, and JSON value. Application services validate the target Entity, effective definition, exact version, and value while locking the Entity row. PostgreSQL validates envelope/reference/scope/type integrity; JSON Schema semantics remain an application validation responsibility.

MSP-owned definitions apply to matching Entity types in the MSP and organization workspaces. Organization-owned definitions additionally apply to matching entities whose organization scope exactly matches the definition owner. Organization definitions never apply to MSP-owned entities. The effective field set is therefore deterministic from the URL-derived workspace and target Entity.

Publishing a new definition version never rewrites existing Entity envelopes. Existing values remain pinned to the version that accepted them and render with that historical version. The API reports whether each value is current and reports compatible/incompatible value counts when a new version is created. Editing a stale value validates it against and repins it to the latest version. Archiving a definition prevents new values while retaining definition versions and historical envelopes.

The `required` marker describes collection policy for workflows that integrate the definition; it does not retroactively invent values for existing entities. Each domain creation workflow must explicitly add atomic required-field enforcement when it adopts custom fields.

## Consequences

- Definition edits remain auditable and migration-safe without treating Git as a transactional revision store.
- MSP standards can be inherited consistently while clients retain narrowly scoped extensions.
- Historical values remain interpretable after labels, choices, or validation rules change.
- Searching and indexing selected custom fields, bulk value migration, Person-association-specific fields, and required-field enforcement during every domain create remain later integrations over this contract.
