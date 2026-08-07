# ADR 0004: Open source and branding

- Status: Accepted pending pre-beta legal review
- Date: 2026-08-07

## Decision

License application code under AGPL-3.0-only, accept contributions under a Developer Certificate of Origin, and govern the official TekDocs name and marks separately. Theming and white-label configuration remain open features.

All dependencies and bundled assets must pass an automated allowlist plus human review for ambiguous cases. Vendor integrations should prefer protocol-level HTTP clients over incompatible proprietary SDKs.
