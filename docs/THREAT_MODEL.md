# Initial Threat Model

## Protected data

Client documentation, credentials, personal/contact information, asset and network inventory, vendor terms and costs, audit history, integration credentials, compliance evidence, and immutable publications.

## Principal threats and planned controls

| Threat | Initial controls |
| --- | --- |
| Cross-client or cross-tenant access | Explicit ownership columns, fail-closed scoped query APIs, same-tenant database triggers including organization classifications and staff assignments, staged transaction-local RLS contract, and a central permission-key policy service. Organization access modes can only narrow role permissions; `assigned_only` requires the owner or an explicit same-tenant membership assignment. Lists, switchers, direct routes, domain APIs, searches, and backlinks share the policy-filtered boundary and a blocking negative-isolation/IDOR matrix. Organization URLs use stable entity identifiers but always resolve through the authenticated tenant. RLS table policies are not yet active. |
| Privilege escalation through role or client-mode administration | Owner identity cannot be reassigned, tenant memberships accept only tenant-scoped built-in roles, role/mode/assignment mutations require catalog permissions plus TOTP and CSRF, submitted role metadata is ignored, targets are tenant-scoped, and audit events contain no role or organization values. Guessed member/client identifiers return non-disclosing failures. Custom and scoped role grants remain unavailable until their own negative-test matrices ship. |
| Assignment mistaken for authorization | Staff assignments target tenant memberships rather than Person names, job titles, or email strings. PostgreSQL rejects cross-tenant assignment edges; the policy service separately requires the requested permission and MFA. Adding or removing an assignment is owner-permission, TOTP, and CSRF protected, idempotent, and value-free in audit metadata. |
| Stale or forged workspace context | Workspace identity is explicit in URLs and API scope, is resolved through tenant and policy boundaries on every request, and never grants access by selection alone. Scope changes clear stale data before loading, creation derives ownership server-side, parallel tabs remain independent, and browser tests assert that responses from a prior workspace cannot appear after a switch. |
| Account takeover | Maintained authentication library, invite-only onboarding, MFA, rate limits, session inventory/revocation, secure recovery. |
| Email disclosure or delivery interception | Central templates, header validation, bounded SMTP timeout, TLS-by-default production validation, paired credentials, loopback-only development inbox, and no message contents in command output. |
| Invitation theft, replay, or enumeration | Owner-only issuance, 256-bit random tokens, digest-only storage, constant-time matching, fragment-based delivery links and immediate browser scrubbing, CSRF-protected transactional acceptance, expiry, resend rotation, revocation, generic unavailable/delivery failures, and value-free audit events. |
| Stored XSS through Markdown | No raw HTML/MDX, server allowlist sanitizer, client defense in depth, CSP, malicious fixture corpus. |
| Credential disclosure | Envelope encryption, external wrapping key, narrow reveal endpoint, reauthentication, audit without values, redaction tests. |
| Malicious integration target | Address validation, private/reserved network blocking, redirect revalidation, time/size limits, signed webhooks, replay cache. |
| Destructive or forged document change | Immutable revisions, optimistic concurrency, append-only audit, signed STATIC manifests, retained supersession chain. |
| Supply-chain compromise | Locked dependencies, Dependabot, dependency review, CodeQL, Gitleaks, Trivy, SBOM, provenance attestations. |
| Backup loss or key loss | Documented encrypted backup, restore rehearsal, separately protected wrapping/signing keys, explicit recovery checks. |

This model must be revised when authentication, RBAC, secret storage, uploads, rendering, client access, or external network behavior changes.
