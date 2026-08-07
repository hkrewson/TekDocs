# Release Roadmap

The authoritative product scope is `docs/PRODUCT_CHARTER.md`. A milestone may close only when its acceptance criteria and relevant release gates have verified evidence.

| Release | Status | Outcome |
| --- | --- | --- |
| 0.0.1 | Complete (local evidence) | Governance, threat model, repository, Docker stack, Django/React skeleton, OpenAPI, CI, design system, and architecture spikes. |
| 0.1.0 | Planned | Secure bootstrap, invite-only authentication, MFA, sessions, OIDC seam, tenant shell, and audit trail. |
| 0.2.0 | Planned | Universal entity registry, organizations/people, custom fields, entity links, search, scoped RBAC, and isolation gates. |
| 0.3.0 | Planned | Markdown editor, reusable blocks, immutable revisions, STATIC publications, signed manifests, and PDF artifacts. |
| 0.4.0 | Planned | Encrypted credentials plus hardware and software inventory. |
| 0.5.0 | Planned | Network inventory and relationship-derived diagrams. |
| 0.6.0 | Planned | Controlled client portal, publication workflow, notifications, and event outbox. |
| 0.7.0 | Planned | Stable API, service credentials, webhooks, integration runtime, reconciliation, and sanitized Git export. |
| 0.8.0 | Planned | Compliance evidence workspace and safe domain/certificate monitoring. |
| 0.9.0 | Planned | Feature freeze, upgrade/restore rehearsal, accessibility, performance, DAST, and external review. |
| 1.0.0 | Planned | Public supported release with signed images, SBOM/provenance, and final operator/security documentation. |

## 0.0.1 acceptance criteria

- [x] `make bootstrap` prepares local dependencies.
- [x] `make check` passes backend and frontend static/unit gates.
- [x] `make test-compose` proves a fresh production-shaped stack and health contract.
- [x] OpenAPI is generated and validated from backend source.
- [x] The React shell provides responsive sectioned navigation, client context, profile access, and administrative routes.
- [x] Markdown, authentication, envelope-encryption, and PDF choices have executable or documented feasibility evidence.
- [x] GitHub CI, Dependabot, CodeQL, secret scanning, dependency review, container scanning, and SBOM workflows are present.

Local closeout evidence and remaining risks are recorded in `docs/releases/0.0.1.md`. Hosted GitHub workflows remain unverified until the repository is published and the first pull request runs.
