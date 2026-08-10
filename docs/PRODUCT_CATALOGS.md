# Product catalogs

TekDocs supplier catalogs are reference data owned by an organization classified as a vendor or manufacturer. Open the supplier from **Organizations**, then choose **Products**. Client-only and partner-only workspaces cannot own product templates.

## Product and model identity

- A **product** is the stable hardware or software family, such as a switch family or software offering.
- A **model** is the stable orderable or deployable template, such as one SKU, edition, or appliance size.
- Both receive universal TekDocs entity identifiers and remain owned by the supplier.
- Archiving a product also archives its active models; retained revisions remain historical data.

Creating an asset from a client workspace selects one active supplier model and creates a separate client-owned entity. TekDocs retains the supplier, product, model, exact current model revision, exact specification-definition version, validated values, and a canonical SHA-256 provenance checksum. Supplier edits never rewrite an existing client asset.

An organization that owns catalog records must retain at least one Vendor or Manufacturer classification. TekDocs permits switching between those classifications, but rejects removing both until the catalog has been retired through a future supported transfer/removal workflow.

## Specification sets

A specification set is a reusable validation contract for hardware or software models. The visual builder supports text, integer, number, yes/no, and choice fields plus required markers. The server stores a closed Draft 2020-12 JSON Schema and calculates its SHA-256 checksum.

Publishing a new specification-set version is append-only. Existing models remain pinned to the version that accepted their values. TekDocs deliberately rejects remote schema references, authored regular expressions, compound evaluators, executable extensions, open-ended properties, oversized schemas, invalid choice lists, and unknown schema vocabulary.

## Model revisions

Every model create or edit appends an immutable revision containing:

- the exact specification-set version;
- validated values;
- lifecycle state;
- revision notes and author;
- parent revision and sequential number;
- a server-calculated content checksum.

An edit must identify the revision it began from. If someone else saves first, TekDocs returns a conflict without overwriting either person's work. Reload the current revision, review the difference, and reapply the intended change.

Catalog reads require `assets.view`; catalog changes require `assets.edit`, CSRF protection, and the centrally declared MFA requirement. Supplier classification narrows this authorization and never grants it.

## Product documentation

A supplier may associate a product, or one exact model under that product, with a `client_visible` STATIC publication owned by the same supplier. Live documents and MSP-internal publications cannot cross this boundary. The association requires both document visibility and asset-management authority.

When a client asset is created, TekDocs copies the applicable product-level and model-level association identities into append-only provenance rows. Each row retains the exact signed publication and content digest. Corrections and newly associated guides affect future assets only; prior assets keep their original projection and retained PDF/artifact access.

## Client vendors

The client Vendors page groups active client assets by their retained supplier identity. It does not copy an organization, match a label, or create an implicit entity relationship. A supplier appears once with the number of active assets that retain it.

Serial numbers, purchasing, assignment, warranty, lifecycle events, costs, and bulk inventory operations begin in later `0.3.x` slices.
