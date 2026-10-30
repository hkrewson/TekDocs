# Shared-block migration (development after 0.9.16)

Supported internal documents can migrate with shared leaf blocks using live or
pinned references. Live references follow source edits; pins keep their selected
revision. An operator previews the complete live dependency group before moving
its documents together. New signed publications preserve the exact composition
and retained files; earlier signed versions and PDFs remain unchanged.

Rollback restores supported Git text edits to the original owners while preserving
pins and retained history. Stale previews, incomplete groups and missing evidence
block the operation. Same-Workspace reuse with one occurrence per Block is
supported; repeated occurrences, templates, dynamic dependencies, cross-Workspace
reuse and client delivery remain excluded.

See the [validation record](../migrations/shared-block-publication-migration.md).
This slice does not publish a new version or deploy production.
