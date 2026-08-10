# ADR 0030: Product publications and retained client asset provenance

- Status: Accepted for `0.3.4`
- Date: 2026-08-10

## Context

Supplier catalog labels and current model data are mutable reference information. Creating a client asset by copying a vendor name, SKU, current specification values, or live document URL would allow later supplier edits to silently change—or make ambiguous—the origin of an installed asset. Supplier documentation also crosses an organization boundary and must not expose an editable or MSP-internal document merely because it is related to a product.

## Decision

Product documentation is an explicit `CatalogProductDocument` association owned by the exact supplier. It joins one stable product, an optional model under that product, and one exact immutable `DocumentPublication` owned by the same supplier. Only a `client_visible` STATIC publication is eligible. A live document, an MSP-internal publication, a publication from another organization, or a model outside the product is rejected. Archiving an association affects future asset creation only; it never removes retained provenance.

A `ClientAsset` is a new client-owned Entity created from one active catalog model. The browser submits the selected model Entity identifier and an optional client-facing asset name. Under locks, the server derives the supplier, product, current model revision, exact specification-definition version, and validated specification values. Those identifiers and values are stored with a canonical SHA-256 provenance checksum. They are not reconstructed from names and are not advanced when the catalog changes.

At creation, TekDocs resolves every active product-level association plus every active association for the selected model. Each exact publication is captured in an append-only `ClientAssetDocumentProvenance` row. Client asset reads project the retained STATIC title, digest, verification status, and retained artifact identities through the client asset authorization boundary. They do not grant general supplier-workspace or supplier-document access.

The client Vendors view is a query projection over active client assets grouped by retained supplier identity. It creates no duplicate organization, inferred label match, or implicit mutable relationship. A later explicit EntityLink may coexist, but is not required for provenance.

All rows carry tenant and exact owning-organization scope. Supplier associations use the supplier scope; assets and asset-document provenance use the client scope. Django validation, transactional services, PostgreSQL relationship guards, forced RLS, append-only provenance triggers, central `assets.view`/`assets.edit` and `documents.view` policy checks, and negative IDOR tests are required together.

## Consequences

- STATIC publication is the cross-organization documentation boundary, reusing its signed manifest, retained PDF, and retained attachment artifacts instead of inventing another snapshot format.
- Correcting supplier documentation creates a new publication and association for future assets; existing assets retain the prior publication.
- This slice establishes asset identity and provenance only. Serials, acquisition/disposal, warranty, assignment, mutable lifecycle events, costs, software installations/licenses, bulk transfer, and attachment-provider hardening remain `0.3.5`–`0.3.9`.
