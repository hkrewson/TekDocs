# ADR 0039: Inventory and credential-reference certification boundary

- Status: Accepted for `0.4.0`
- Date: 2026-08-11

## Decision

TekDocs `0.4.0` certifies the external credential-reference and operational inventory foundation implemented in `0.3.1` through `0.3.12`. It adds no inventory model, migration, route, provider capability, credential-value custody, import field, or cross-client reporting projection. ADR 0020 and ADRs 0029–0038 remain the behavioral and security contract.

The dedicated `make test-inventory-certification` gate runs against PostgreSQL and composes supplier catalogs, retained asset and publication provenance, hardware lifecycle, software installations and entitlements, contracts and cost projection, credential references, hostile attachment intake, typed asset relationships, recycle-bin recovery, the authenticated-route and IDOR matrix, raw non-owner forced-RLS checks, migration preservation, competing seat allocation, CSV/bulk atomicity, and the authorization-aware inventory reference dataset. It is a required dependency of `make release-gate`; it does not replace the browser matrix, real browser-to-Django-to-PostgreSQL journey, security scans, production-image and clean-install rehearsals, general oldest-supported upgrade, or inventory-specific upgrade and database/media recovery rehearsals.

The certification applies to one MSP per installation. MSP operational surfaces resolve only the explicit MSP Workspace and never aggregate client records. Organization surfaces resolve one exact organization Workspace. Customer credential values remain outside TekDocs; certification covers only strict external pointers and the authorization/audit handoff boundary. The built-in attachment scanner remains a structural and content defense-in-depth implementation rather than a maintained malware-signature service.

## Consequences

- `0.4.0` is a release boundary, not another inventory feature slice.
- Future changes to inventory ownership, provenance, lifecycle, entitlement, protected-cost, attachment, relationship, import/export, or credential-provider behavior must extend the certification composition and update the governing ADRs.
- Network inventory may begin at `0.4.1` using the certified explicit-Workspace and policy boundaries without treating network scope as tenant-wide aggregation.
- Local certification evidence may be recorded, but hosted checks, tags, images, attestations, and deployments require separate authorization.
