# Workspace search

TekDocs search is a read-only discovery surface over the active MSP or organization workspace. It searches authorized document titles and resolved Markdown together with an explicit allowlist of operational identifiers, including names, asset tags, serial numbers, model numbers, site and location codes, domains, certificate hostnames, network addresses, CIDRs, DNS records, circuit references, license references, services, and attachment filenames.

Every request resolves the URL-selected workspace and the caller's permissions before candidates, excerpts, counts, or facets are produced. MSP search covers MSP-owned records and organization search covers only the selected authorized organization. Archived, sibling-workspace, other-tenant, MSP-private client-portal data, withheld content, and permission-denied records cannot contribute a result, excerpt, count, or facet.

## API contract

- `GET /api/v1/search` searches the MSP workspace.
- `GET /api/v1/workspaces/organizations/{organization_entity_id}/search` searches one organization workspace.
- `q` is required and contains 2–80 characters.
- `result_type` is optional and accepts a maintained public result family.
- `page` is limited to 1–100; `page_size` is limited to 1–25.
- Responses contain a normalized type, title, safe excerpt, workspace label, deterministic score, update time, review state when applicable, and an in-application target.

The implementation uses PostgreSQL, applies a two-second database statement budget, and evaluates no more than 1,000 authorized candidates and 12 query terms. Results use exact-title, title-prefix, title-content, exact-identifier, identifier-prefix, identifier-content, and document-body tiers, then a stable label/type/UUID tie-break. Excerpts are limited to 240 characters. Credentials, credential provider links, audit metadata, financial values, provider payloads, custom fields, hidden content, and secrets are not search inputs.

This is lexical search. Vector search, generative answers, OCR, cross-tenant federation, and an external search service are outside the 1.0 contract.
