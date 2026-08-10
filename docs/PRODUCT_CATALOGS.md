# Product catalogs

TekDocs supplier catalogs are reference data owned by an organization classified as a vendor or manufacturer. Open the supplier from **Organizations**, then choose **Products**. Client-only and partner-only workspaces cannot own product templates.

## Product and model identity

- A **product** is the stable hardware or software family, such as a switch family or software offering.
- A **model** is the stable orderable or deployable template, such as one SKU, edition, or appliance size.
- Both receive universal TekDocs entity identifiers and remain owned by the supplier.
- Archiving a product also archives its active models; retained revisions remain historical data.

Client assets are not created in `0.3.3`. The `0.3.4` provenance workflow will create a new client-owned asset while retaining links to the exact supplier product, model, specification revision, and related documentation.

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
