# Release Go/No-Go Checklist

## Required evidence

- Version, roadmap status, migration state, OpenAPI, and release notes agree.
- Fresh Docker install and previous supported-version upgrade pass.
- `make release-gate` passes, or each unavailable local gate has successful hosted evidence.
- Authentication, RBAC, tenant/client isolation, secret redaction, static-publication integrity, and browser regression pass for the shipped scope.
- Dependency, license, Gitleaks, CodeQL, Trivy, and DAST findings have no unresolved Critical or untriaged High issues.
- Backup and restore include the database and artifacts; wrapping and publication keys are recovered separately.
- Container digests, CycloneDX SBOMs, provenance attestations, signed tag, and release notes are ready.
- User/operator/security documentation reflects the running release.

Do not publish, tag, push images, or deploy without explicit authorization and a recorded go/no-go decision.
