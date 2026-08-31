# Release Go/No-Go Checklist

## Required evidence

The release record identifies the candidate commit and contains links or immutable references for every item below. “Passed” without the underlying result is not evidence.

- Version, roadmap status, migration state, OpenAPI, and release notes agree.
- The checked-in TypeScript API client matches OpenAPI, public error/pagination/filter contracts pass, and every advertised idempotent operation documents its actual replay boundary.
- Fresh Docker install and previous supported-version upgrade pass.
- The representative migration cycle preserves identifiers, authorization state, archive/audit evidence, and the forced-RLS inventory.
- Reference-dataset latency and query-count budgets pass without bypassing policy or workspace scope.
- `make release-gate` passes, or each unavailable local gate has successful hosted evidence.
- Authentication, RBAC, tenant/client isolation, secret redaction, static-publication integrity, and browser regression pass for the shipped scope.
- Playwright passes against the development application and the production-shaped Compose stack, including the live browser-to-Django-to-PostgreSQL workspace journey.
- A named human tester completes the release workflows in development and in a representative real-world deployment; record the version, environment, workflows, result, and unresolved findings.
- A documentation validation release runs `make test-documentation-validation` plus its prior-alpha upgrade and database/media restore rehearsals.
- An inventory validation release runs `make test-inventory-validation` plus its prior-stabilization upgrade and database/media restore rehearsals.
- A network validation release runs `make test-network-validation` plus its prior-stabilization upgrade and database/media restore rehearsals.
- A controlled-client-access validation release runs `make test-portal-notification-validation`, the real publisher/approver/client browser journey, its exact-prior upgrade, and database/media restore rehearsals.
- A file/export stabilization release runs `make file-export-release-gate`, including hostile input, scoped session/token reads, full/range downloads, browser engines, exact-prior upgrade, database/media recovery, security scans, and production-image rehearsal.
- A graphical-diagram export release runs `make diagram-export-release-gate`; production evidence must include the network-disabled renderer, deterministic SVG/PNG bytes, hostile-source rejection, cleanup, graphical HTML/PDF/DOCX/ZIP, STATIC fail-before-promotion, retained artifact integrity, and accessible source fallback.
- Dependency, license, Gitleaks, CodeQL, Trivy, and DAST findings have no unresolved Critical or untriaged High issues.
- Backup and restore include the database and artifacts; wrapping and publication keys are recovered separately.
- Container digests, CycloneDX SBOMs, provenance attestations, signed tag, and release notes are ready.
- User/operator/security documentation reflects the running release.
- The product capability matrix, backend payload inventory, frontend registry, routes, navigation, help, and browser exclusions agree.
- Production backend, frontend, and renderer image digests are recorded with SBOM and provenance-attestation verification results.
- The supported previous-minor upgrade matrix and the documented final-0.9-to-1.0 rehearsal pass; backup restoration starts with the producing version before normal upgrade.
- The independent security assessment from #38 has a disposition for every finding; no Critical or untriaged High finding remains.
- Chromium, Firefox, WebKit, targeted mobile, keyboard, and axe results are attached or linked without retaining sensitive browser artifacts.
- Pilot issue #39 records each participating MSP environment, completed workflow set, result, unresolved finding, and explicit go/no-go disposition without customer-sensitive data.
- Every intentionally deferred capability is listed by issue number and agrees with `docs/PRODUCT_BOUNDARY.md`.

Do not publish, tag, push images, or deploy without explicit authorization and a recorded go/no-go decision.
