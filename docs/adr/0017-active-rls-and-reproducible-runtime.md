# ADR 0017: Active RLS and reproducible runtime inputs

- Status: Accepted for `0.1.14`
- Date: 2026-08-09

## Decision

TekDocs separates PostgreSQL duties into a migration owner and a fixed application runtime role. A one-shot Compose migration service provisions the login role and applies Django migrations with owner credentials. Web, worker, and scheduler processes receive only the runtime credential. Production startup refuses a superuser, table owner, `BYPASSRLS` role, an unexpected role name, or an incomplete RLS policy inventory.

The runtime role receives data-manipulation and sequence privileges but no schema-creation or migration authority. Every implemented core table carrying a tenant identifier uses forced row-level security. Tables with a direct nullable organization scope use `tekdocs_scope_matches` for both `USING` and `WITH CHECK`; tenant-wide registries and control records match the exact transaction-local tenant. Organization anchors remain tenant-wide MSP registry records so an authorized user can resolve a workspace before entering it. Authentication-provider tables and the accounts authorization control plane remain outside organization RLS because they establish identity and policy rather than contain client domain data; cross-tenant application tests and final `0.2.0` certification remain mandatory for that boundary.

An RLS middleware opens one transaction around authenticated session requests, derives the single-installation tenant without accepting ownership from the browser, and binds MSP scope. After Django's CSRF view check, it resolves any organization route inside that tenant and rebinds exact organization scope; the view still must authorize through the central policy service before returning data or mutating state. This ordering preserves CSRF-first denial semantics and treats scope as a database boundary rather than a permission grant. Scope settings use transaction-local `set_config` and are verified empty after transaction completion. Sessionless public endpoints do not open the request transaction. Anonymous bootstrap and invitation acceptance bind only inside their service transaction after resolving or creating the owning tenant. Background jobs and operator commands must use the explicit scope context manager and fail closed when omitted.

Python installations consume reviewed, hash-locked production or development requirements. Container images and local security tools use immutable digests. GitHub Actions use commit SHAs annotated with their tracked release so Dependabot can continue proposing upgrades. A local workflow syntax/lint gate verifies the checked-in specifications; only an observed hosted run may be called hosted evidence.

## Consequences

- Accidentally unscoped ORM and raw-SQL access to implemented core tenant data returns no rows under the runtime role.
- An organization-scoped request cannot read or write a sibling organization's directly scoped rows even if an application query omits its filters.
- Migration and runtime credentials have separate custody and rotation responsibilities.
- Tenant-wide registry rows still require the central policy service for client reachability and field/audience decisions; RLS is defense in depth, not a replacement for RBAC.
- Hosted automation remains externally blocked until the user authorizes publishing and repository configuration.
