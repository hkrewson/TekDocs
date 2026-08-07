# Initial Threat Model

## Protected data

Client documentation, credentials, personal/contact information, asset and network inventory, vendor terms and costs, audit history, integration credentials, compliance evidence, and immutable publications.

## Principal threats and planned controls

| Threat | Initial controls |
| --- | --- |
| Cross-client or cross-tenant access | Explicit ownership columns, central policy service, scoped query APIs, database constraints/RLS, IDOR regression matrix. |
| Account takeover | Maintained authentication library, invite-only onboarding, MFA, rate limits, session inventory/revocation, secure recovery. |
| Stored XSS through Markdown | No raw HTML/MDX, server allowlist sanitizer, client defense in depth, CSP, malicious fixture corpus. |
| Credential disclosure | Envelope encryption, external wrapping key, narrow reveal endpoint, reauthentication, audit without values, redaction tests. |
| Malicious integration target | Address validation, private/reserved network blocking, redirect revalidation, time/size limits, signed webhooks, replay cache. |
| Destructive or forged document change | Immutable revisions, optimistic concurrency, append-only audit, signed STATIC manifests, retained supersession chain. |
| Supply-chain compromise | Locked dependencies, Dependabot, dependency review, CodeQL, Gitleaks, Trivy, SBOM, provenance attestations. |
| Backup loss or key loss | Documented encrypted backup, restore rehearsal, separately protected wrapping/signing keys, explicit recovery checks. |

This model must be revised when authentication, RBAC, secret storage, uploads, rendering, client access, or external network behavior changes.
