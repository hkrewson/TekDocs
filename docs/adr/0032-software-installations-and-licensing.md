# ADR 0032: Client software installations and entitlement allocation

- Status: Accepted for `0.3.6`
- Date: 2026-08-10

## Decision

Each client asset whose retained supplier product is software receives one `ClientSoftwareInstallation` current-state profile. Installation identity remains the client asset Entity; the profile records deployment state, installed version and dates, verification date, and an optional exact-client site. Uninstalled is terminal through ordinary workflows.

A `SoftwareLicense` is a separate addressable client Entity related to one retained supplier software product and optional model. It records entitlement kind and state, a positive seat limit, term and renewal behavior, and a bounded provider or contract reference. TekDocs does not accept license keys, activation secrets, usernames, passwords, or provider API credentials.

`SoftwareLicenseInstallation` explicitly relates a license to each covered installation of the same retained product. `SoftwareLicenseSeat` is a retained allocation numbered within the license and may identify an exact-client person, a covered installation, or both. Revocation timestamps the allocation rather than deleting it. Every material license mutation appends a value-minimized `SoftwareLicenseEvent`; history excludes references and other free text and is immutable in Django and PostgreSQL.

All reads use `assets.view` and all mutations use MFA/CSRF-protected `assets.edit`. Services lock the license for seat-limit decisions. Scoped query managers, exact-client lookup, PostgreSQL relationship guards, forced RLS, authenticated-route inventory, and sibling/cross-tenant tests provide defense in depth.

## Consequences

- Entitlements can cover multiple deployments without conflating a license with an installed asset.
- Seat history remains interpretable after revocation while active counts stay direct.
- Renewal dates are inventory state in this slice; scheduled reminders and notifications arrive with the notification subsystem.
- Costs, purchasing contracts, license-file attachments, bulk operations, and provider reconciliation remain later slices.
