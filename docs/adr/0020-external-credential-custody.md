# ADR 0020: External credential custody

Status: Accepted

## Context

TekDocs needs to tell technicians which credential applies to an asset, service, or procedure. Storing the credential value inside the same application that holds the client's operational map would materially increase the impact of a TekDocs host compromise. Envelope encryption does not solve that threat when an attacker controls both the application process and the deployment key source.

## Decision

TekDocs stores credential references, never customer credential values. The first provider is a 1Password Private Link that identifies an item while leaving reveal, authorization, unlock, and audit inside 1Password. TekDocs opens the provider link and does not call a secret-retrieval API, proxy a revealed value, cache it, index it, export it, or place it in notifications.

Only provider-specific, strictly validated reference formats are accepted. Public 1Password share links and arbitrary URLs are rejected. A reference has its own TekDocs scope, RBAC, lifecycle, and value-free audit events; possession of a TekDocs reference does not grant access to the referenced vault item.

For the first adapter, TekDocs accepts only the canonical HTTPS link currently produced by **Copy Private Link**: host `start.1password.com`, path `/open/i`, and exactly one account (`a`), vault (`v`), item (`i`), and 1Password account-host (`h`) parameter in canonical order. This grammar is an intentionally strict compatibility contract inferred from current provider output because 1Password documents the feature semantics but does not publish a stable machine-readable URL grammar. Provider changes therefore fail closed until fixtures and the adapter are deliberately reviewed.

Application runtime secrets remain a separate deployment concern. They must be supplied through files or a deployment secret manager and are never modeled as customer credentials. A documented 1Password CLI/operator workflow may inject those runtime values, but TekDocs itself receives only the resulting deployment inputs.

## Consequences

- Native customer-secret storage, reveal endpoints, key rotation, and secret export are removed from the pre-1.0 roadmap.
- A compromised TekDocs host can expose reference metadata and provider links, but not customer credential values held by the provider.
- Provider availability and stale/moved items require clear UI states and operator guidance.
- The first implementation is intentionally 1Password-specific while using a small provider contract that can admit other non-retrieving link providers later.
