# 1.x compatibility and deprecation policy

## API

The supported v1 API is additive throughout 1.x. Existing fields, operations, meanings, and authorization boundaries are not removed or narrowed without advance deprecation in the API description, release notes, and upgrade guide. New response fields are optional for clients. A removal requires a replacement path, at least one supported minor release of notice, and a documented migration.

## Database and upgrades

Django migrations are the only schema and data-upgrade authority. Operators must not edit the schema manually or run an older application against a database migrated by a newer version.

TekDocs supports upgrading from the latest patch of the previous supported minor release. The 1.0 release additionally provides and rehearses a documented upgrade from the final supported 0.9 patch. Skipped-minor upgrades must proceed through supported intermediate versions unless the release guide explicitly says otherwise.

## Backups and restore

A backup is restored with the exact TekDocs version and compatible keys that created it. After restore verification, the installation is upgraded through the normal supported migration path. A backup is not a cross-version import format.

## Portable artifacts

Publication manifests and sanitized Git exports created by any 1.x release remain readable throughout 1.x. New fields are optional to older readers or use an explicitly versioned envelope. Existing identifiers, checksums, revision references, signatures, and audience semantics are not silently reinterpreted.

## Deprecation record

Every deprecation names the affected API or artifact, first deprecated version, replacement, last supported version, migration instructions, and removal issue. Security fixes may restrict unsafe behavior sooner, but must preserve data recovery and document the exception.

