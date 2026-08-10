# ADR 0029: Supplier product catalogs and versioned specifications

- Status: Accepted
- Date: 2026-08-09

## Decision

Vendor- and manufacturer-classified organization workspaces may own product catalogs. A `CatalogProduct` is the stable, addressable product-family identity and is explicitly hardware or software. A `CatalogModel` is the stable, addressable orderable or deployable template beneath one product. Partner-only and client-only workspaces cannot own catalog records. Organizations with multiple classifications retain one identity and may own a catalog when either the vendor or manufacturer classification is active.

Products and models remain supplier-owned reference data. A later client asset will retain provenance to the exact supplier product, model, model revision, specification-definition version, and applicable documentation rather than moving or copying supplier identity.

Specifications use stable `CatalogSpecificationDefinition` records with immutable sequential `CatalogSpecificationDefinitionVersion` children. Each version contains a server-validated Draft 2020-12 JSON Schema plus a server-calculated SHA-256 checksum. The accepted schema vocabulary is deliberately bounded: one closed object, ordinary named properties, supported scalar/string-array value types, required keys, enums, simple numeric and string-length bounds, and no remote references, authored regular expressions, compound evaluators, or executable extension vocabulary.

Each model change creates an immutable sequential `CatalogModelRevision` containing the exact definition-version identifier, validated specification values, lifecycle state, notes, author, timestamp, parent revision, and server-calculated checksum. Existing revisions are never reinterpreted when a definition changes. Updates require the caller's exact current revision identifier; stale writes return a conflict and do not overwrite either revision.

Catalog reads and mutations use the central `assets.view` and `assets.edit` permissions. Supplier classification is an additional hard constraint and never a permission grant. Every row carries tenant and exact supplier organization scope; scoped managers, same-scope database guards, forced PostgreSQL RLS, authenticated-route inventory, and sibling/cross-tenant negative tests provide defense in depth.

Once an organization owns a product or specification definition, application validation and a PostgreSQL classification guard require it to retain at least one vendor or manufacturer classification. A vendor-to-manufacturer (or reverse) transition inserts the replacement classification before removing the old one so the invariant remains true throughout the transaction.

## Consequences

- Product and model identity is reusable without conflating supplier templates with client-owned assets.
- Specification evolution remains interpretable and migration-safe without an EAV-only schema or Git as the transactional history store.
- Product documentation, client asset instantiation, provenance projection, relationship-derived client vendors, costs, attachments, and bulk transfer remain in `0.3.4`–`0.3.9`.
- Schema authoring is an administrative technical workflow. The browser provides a bounded structured schema form and a reviewed advanced JSON view; the server remains authoritative for vocabulary and validation.
