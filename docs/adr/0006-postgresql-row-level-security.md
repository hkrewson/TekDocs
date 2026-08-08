# ADR 0006: PostgreSQL row-level security activation strategy

- Status: Accepted
- Date: 2026-08-08

## Decision

Application policy and explicit scoped query managers remain the first authorization boundary. PostgreSQL row-level security will provide a second boundary through transaction-local settings named `tekdocs.tenant_id`, `tekdocs.organization_id`, and `tekdocs.organization_mode`.

The organization mode has three deny-by-default meanings:

- `msp`: permit only tenant-owned rows whose organization is null;
- `organization`: require an exact organization identifier within the current tenant;
- `all`: permit organization-owned rows only after the application policy has established MSP-wide authority.

The runtime database role will be separate from the migration owner, have neither `SUPERUSER` nor `BYPASSRLS`, and will not own application tables. Policies use both `USING` and `WITH CHECK`. The application binds settings only with transaction-local `set_config(..., true)` calls inside an atomic transaction so pooled connections cannot retain a prior request's scope.

The `0.1.1` slice installs the stable database helper functions and application binding contract but does not enable table policies. Activation is deliberately staged until bootstrap, anonymous invitation/password-token redemption, migrations, workers, and operator commands have narrow tested execution paths. Pre-authentication token resolution must not receive a general web-role bypass; it will use a purpose-specific database function or separately constrained service boundary before policy activation.

## Consequences

Tests can validate policy inputs and scope semantics now without creating a false claim that RLS protects the runtime role. A later activation migration must prove the runtime role cannot read or write another tenant/client even through raw SQL, cannot select `all` organization mode without an authorized application path, and cannot retain settings after transaction completion. Deployment validation must reject an owner or `BYPASSRLS` runtime role once policies become active.
