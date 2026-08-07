# ADR 0005: Document ownership and listing scopes

- Status: Accepted
- Date: 2026-08-07

## Decision

Give every document exactly one authoritative ownership scope within its tenant: either the MSP scope or one client organization. Ownership determines the document's canonical location and which scoped permissions may edit, archive, or publish it.

Represent additional Documentation-index placement as an explicit, permission-aware reference rather than a copy. An MSP-owned live document may be referenced into any number of client indexes. Each client listing resolves the same document identity and current authorized content, so an owner-authorized edit is reflected everywhere that live document is listed. A reference may instead target a specific STATIC publication when immutable output is required.

A listing reference does not transfer ownership, duplicate blocks, grant edit permission, or make MSP-private material visible to client portal users. Client audience publication remains a separate explicit action. The UI must identify externally owned entries, such as “MSP reference,” and distinguish live documents from STATIC publications.

For 1.0, client-owned documents may appear in their owning client and MSP administrative views but may not be referenced laterally into another client. Removing a listing reference removes only that placement. Archiving a referenced source document must surface and safely resolve every affected listing.

## Consequences

Document queries return the permission-filtered union of documents owned by the selected scope and references placed into that scope. The data model needs separate ownership and listing-reference records, uniqueness constraints for repeated placement, backlinks, and negative tests proving that references cannot bypass tenant, client, audience, or edit boundaries.
