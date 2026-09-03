# ADR 0100: Keep HaloPSA authoritative through a read-only projection

- Status: Accepted
- Date: 2026-09-02
- Issue: [#36](https://github.com/hkrewson/TekDocs/issues/36)

## Context

Technicians need client, contract, and current ticket context beside documentation. TekDocs deliberately excludes native ticketing, while HaloPSA already owns service-desk workflow, messages, attachments, SLA processing, and ticket history. Copying unrestricted ticket records would duplicate that system of action and increase the amount of customer communication and secret material held by TekDocs.

## Decision

TekDocs provides an MSP-managed, read-only HaloPSA adapter using OAuth 2.0 client credentials through the protected integration-egress boundary. It observes allowlisted client, site, contact, contract, and ticket fields. Tickets are limited to open records and records closed within 90 days; bodies, email, notes, attachments, credentials, and custom fields are discarded before persistence.

External identities are connected to TekDocs entities through stable, tenant-owned mappings. A unique exact business identifier can be matched automatically, while ambiguous, absent, retired, or manually chosen relationships use the reconciliation workflow. A provider rename updates the observation fingerprint without changing the mapped TekDocs entity.

Mapped ticket summaries are available only to authorized MSP staff in the selected client workspace and in workspace search. They link back to the same HaloPSA origin. They are absent from the client portal, publication output, Git exports, handoff bundles, audit metadata, and logs. Provider failure never blocks documentation; retained ticket summaries are marked stale.

## Consequences

HaloPSA remains authoritative for every ticket action and for full ticket content. TekDocs must maintain pagination, bounded retries, stale-state signaling, mapping isolation, and strict projection tests as the HaloPSA API evolves. Any future write capability requires a separate decision, permission model, provider scope, and user approval flow.
