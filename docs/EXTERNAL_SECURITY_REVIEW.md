# External security review intake

TekDocs `0.8.9` requires an independent security review of a frozen, exact commit. Local tests, DAST, static analysis, dependency scans, and internal code review are prerequisites; they are not substitutes for an independent assessment.

## Required scope

The reviewer receives architecture and threat-model context plus a production-shaped deployment containing synthetic data. At minimum the assessment covers:

- owner bootstrap, invitations, password recovery, sessions, TOTP/recovery, OIDC, and reauthentication;
- central policy evaluation, custom/scoped roles, client reachability, MSP-private data, field-level cost projection, client portal separation, IDOR, and PostgreSQL forced RLS;
- Markdown rendering, reusable blocks, entity mentions, attachments/quarantine, immutable publications, PDFs, exports, and browser sinks;
- credential-reference custody, deployment secret files, encryption/signing keys, logs, backups, restores, and migration/runtime database roles;
- tokens, webhooks, provider connections, synchronization workers, Git export, notifications, and transactional outbox behavior;
- approved outbound egress, redirects, DNS rebinding, domain/certificate monitoring, upload/archive payloads, request bounds, rate limits, and availability abuse;
- production images, reverse-proxy assumptions, headers, cookies, CORS/CSRF, dependency/supply-chain controls, operator guidance, and upgrade/rollback paths.

The review must distinguish application findings from deployment assumptions and must avoid placing exploit payloads, credentials, customer data, raw reports, or secret-bearing screenshots in the public repository.

## Finding record

`.github/external-security-review.json` is the value-minimized release record. The private report remains with the project owner or reviewer; `report_reference` identifies it without embedding sensitive content. Every public finding record contains:

- a stable identifier, title, severity, and lifecycle status;
- a concise disposition with no exploit secret or customer information;
- repository evidence paths, tests, or commit identifiers demonstrating resolution;
- `resolved` status for every Critical or High finding before certification.

Medium/Low findings may be explicitly accepted only with documented reasoning, an owner, and a follow-up milestone in the disposition. Critical and High findings cannot be accepted for `0.8.9`.

## Gate

Run `make external-security-review-gate`. It fails unless the review is complete, names the reviewer and exact 40-character commit, includes a timezone-aware completion timestamp and report reference, fully triages every finding, and has no unresolved Critical/High result.

The checked-in initial state is deliberately `not_started`. An empty findings array cannot pass without real review metadata, but metadata alone is not proof that the claimed assessment occurred. The maintainer must verify the reviewer, private report, scope, and remediation evidence before changing the status.
