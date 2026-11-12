# CodeQL alert triage and provider fingerprint hardening

Roadmap slice: reduce the pre-1.0 code-scanning queue to shipped-code findings
and close the provider-record fingerprint boundary reported by CodeQL alert #202.

Acceptance criteria:

- CodeQL continues to run `security-extended` and `security-and-quality` for
  shipped Python and JavaScript/TypeScript sources.
- Test modules, browser rehearsals and isolated operator fixtures do not create
  product code-scanning alerts.
- A provider observation fingerprint is derived only from its allowlisted
  `safe_projection`; excluded provider fields cannot affect retained state.
- The common provider-page validator rejects a digest that does not match the
  safe projection before an observation can be persisted.
- Stable Microsoft permission fingerprints and NinjaOne software identities keep
  their existing algorithms and values.
- Observation schema v2 identifies the new data-minimized fingerprint contract;
  historical v1 observations remain append-only and readable.

## November 8, 2026 intake

The authenticated GitHub inventory contained 463 open CodeQL alerts: 9 high,
128 medium and 326 without a security severity. Dependabot vulnerability and
secret-scanning queues were both empty. Of the security-severity results, nine
were confined to tests or isolated rehearsal fixtures. Eight high results were
test assertions, Git object-identity verification, or intentionally local
mode-0600 acceptance credential files and were not shipped product paths.

The remaining high result reached shipped integration code. HaloPSA fixtures
demonstrated that password-shaped custom fields, private notes and ticket details
were excluded from `safe_projection` but still influenced the deterministic hash
of the full provider record. Similar excluded fields could affect NetBox, UniFi
and Microsoft Graph observation hashes. Those hashes are persisted in immutable
observations and reconciliation state, so the full-record digest violated the
value-minimization boundary even though it was not a password verifier.

The remediation fingerprints the allowlisted projection and enforces that rule
at the shared pre-persistence validator. It deliberately does not convert the
generic stable-identity helper to HMAC: doing so would invalidate Microsoft
permission-scope checks and change NinjaOne software remote identities. Provider
tests cover excluded-field stability, allowlisted-field sensitivity and rejection
of forged observation digests. Exact-source hosted CodeQL is the final alert
disposition authority.

The post-implementation bypass review also checked the v1-to-v2 lifecycle. A
supported NetBox prefix with a historical raw-record fingerprint is relinked to
the projection fingerprint before conflict comparison, so an unchanged first v2
sync does not create a false review item. Complete-type and delta-prefix
retirement tests independently seed historical v1 digests and prove that new
retirement rows use schema v2 plus the empty safe-projection fingerprint instead
of copying the historical digest. Exact fixtures pin the existing Microsoft
permission-scope and NinjaOne software-identity values.

The 127 shipped-code `py/stack-trace-exposure` results entered a separate
API-error contract slice because they required exception-by-exception review;
many exposed intentional domain conflicts while others could reveal internal
details. That later [response-hardening work](exception-response-hardening.md)
reached zero open stack-trace findings without dismissals in exact-source Build
43139510245. This provider/source-scope change does not claim that later result
as part of its own implementation.
