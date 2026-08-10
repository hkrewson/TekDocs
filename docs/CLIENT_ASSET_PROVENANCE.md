# Client asset provenance

## Operator workflow

1. Open a Vendor or Manufacturer workspace and create a specification set, product, and model.
2. Create the supplier documentation that should follow the product. Publish it as STATIC with audience **Client visible**.
3. Open **Products**, select the product, and associate the STATIC publication with all models or one exact model.
4. Open a Client workspace and choose **Assets**. Search supplier models, choose one, optionally give the client asset a local display name, and create it.
5. Inspect the retained model revision, specification version, values, checksum, and product publications from the asset detail. **Vendors** now includes the retained supplier.

## Retention behavior

Asset creation is a snapshot boundary. TekDocs retains identifiers rather than copying supplier labels as provenance. Later supplier model revisions, specification-set versions, publication corrections, association removal, or display-name changes do not rewrite an existing asset. New assets use the supplier state current at their own creation time.

Documentation must already be an immutable, cryptographically verified, client-visible STATIC publication. A live document or MSP-internal publication cannot be associated. The client reads sanitized retained HTML and retained publication artifacts through the asset route; that route does not grant access to the supplier workspace.

## Authorization and isolation

- Supplier catalog/document reads require their central read permissions; association changes require `assets.edit`, `documents.view`, MFA, and CSRF.
- Client asset and derived-vendor reads require `assets.view`; asset creation requires `assets.edit`, MFA, and CSRF.
- Exact route scope, scoped managers, PostgreSQL guards, immutable provenance triggers, and forced RLS reject sibling-client and forged supplier relationships.
- PostgreSQL exposes a narrow read-only client projection for supplier catalog rows and associated client-visible STATIC publication data. It does not expose unrelated supplier documentation and never permits a client-scope catalog write.

Serial numbers, acquisition/disposal, assignments, warranties, mutable lifecycle events, costs, and bulk operations are intentionally deferred to later inventory slices.
