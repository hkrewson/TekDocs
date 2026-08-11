# Release Go/No-Go Checklist

## Required evidence

- Version, roadmap status, migration state, OpenAPI, and release notes agree.
- Fresh Docker install and previous supported-version upgrade pass.
- The representative migration cycle preserves identifiers, authorization state, archive/audit evidence, and the forced-RLS inventory.
- Reference-dataset latency and query-count budgets pass without bypassing policy or workspace scope.
- `make release-gate` passes, or each unavailable local gate has successful hosted evidence.
- Authentication, RBAC, tenant/client isolation, secret redaction, static-publication integrity, and browser regression pass for the shipped scope.
- A documentation certification release runs `make test-documentation-certification` plus its prior-alpha upgrade and database/media restore rehearsals.
- An inventory certification release runs `make test-inventory-certification` plus its prior-stabilization upgrade and database/media restore rehearsals.
- A network certification release runs `make test-network-certification` plus its prior-stabilization upgrade and database/media restore rehearsals.
- Dependency, license, Gitleaks, CodeQL, Trivy, and DAST findings have no unresolved Critical or untriaged High issues.
- Backup and restore include the database and artifacts; wrapping and publication keys are recovered separately.
- Container digests, CycloneDX SBOMs, provenance attestations, signed tag, and release notes are ready.
- User/operator/security documentation reflects the running release.

Do not publish, tag, push images, or deploy without explicit authorization and a recorded go/no-go decision.
