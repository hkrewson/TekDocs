# Phase 8 production-image acceptance

Checkpoint date: 2026-09-25. Version: 0.8.46.

`make production-image-rehearsal` passed against a disposable stack assembled from
the production Compose overlays and production image targets. It exercised the
packaged frontend, backend, migration job, worker, scheduler, PostgreSQL, Valkey,
mail service, ClamAV scanner, and diagram renderer. No existing user or demo data
was mounted into the rehearsal.

The acceptance boundary verified:

- frontend-to-backend readiness and a fully applied migration set;
- absence of development-only test packages in the backend image;
- the configured ClamAV production scanner through an actual stream scan;
- SVG and PNG output through the packaged, network-isolated diagram renderer;
- recorded and running Chromium version agreement plus readable application files;
- non-root users, read-only root filesystems, dropped Linux capabilities,
  no-new-privileges, and bounded process counts for applicable services;
- file-backed secret mounting with service-specific visibility and no secret values
  in container environments, image history, the generated environment file, or
  combined service logs; and
- fail-closed rejection when a secret is supplied through both direct and file
  sources, without disclosing the value or host secret path.

The production-image state is enforced from `acceptance.json` by
`scripts/check-responsive-acceptance.py`. Production route refresh behavior remains
covered by `production-route-acceptance.md`. Human technician and assistive-
technology review plus the full final release gate remain open. This evidence does
not authorize deployment, publication, a version change, or a release.

## Git-backed candidate recurrence — 2026-10-12

Candidate commit `b987fe738b47097654ffffad01d27357e18fa9cb` (tag `v0.9.7`)
passed `make dast`. The isolated production-target rehearsal built and started
the production images, applied migrations, verified repository persistence and
runtime isolation, then ran the pinned unauthenticated ZAP baseline against 12
URLs. Result: 62 PASS, 0 configured FAIL, and 5 passive warnings. The warnings
were suspicious comments, cacheable content, inline styles in the CSP,
modern-web-application detection, and missing/invalid COEP. The raw scan report
is not retained by policy; the repeated scan and candidate-specific warning
dispositions are recorded in [security acceptance](phase-8-security-review.md).
The rehearsal's cleanup removed only its
isolated Compose project and volumes.

This verifies the production image and unauthenticated DAST boundary for the
Git-backed candidate. It does not exercise authenticated workflows or complete
the automated/AI-assisted source review, performance acceptance, human
walkthroughs, or the complete 0.9.8 release gate. An independent external
security assessment is not a release requirement.

## Managed document attachment review — 2026-10-12

A bounded source review traced managed document attachment upload, replacement,
archive, and download through the MSP and organization routes. The route handlers
resolve the caller's workspace and required document permission before operating;
attachment lookup is scoped to the caller's tenant, parent document, clean scan
status, and non-archived state. Repository-authority checks and write guards are
in the shared attachment service path. No concrete issue was identified in this
slice.

The focused Docker-backed regression run passed (exit code 0):
`test_attachment_security.py`, `test_permission_idor_matrix.py`,
`test_document_migration_inventory.py`, and `test_runtime_rls.py`. This evidence
supports only the managed-attachment authorization and authority slice; it does
not substitute for the pending complete 0.9.8 candidate security review or the
remaining release acceptance items.

A second bounded review checked offline validation of source-snapshot ZIPs.
Manifest shape, canonical IDs, safe Markdown paths, archive entry types, entry
inventory, byte/file ceilings, checksums, parsed content identity, and reachable
historical dependency roles are verified; the validator explicitly does not
authenticate a snapshot against Git or claim it is a backup. The adversarial
`test_repository_source_validation.py` suite passed (14 tests, exit code 0).
Five focused `test_content_authoring.py` checks also passed (exit code 0),
covering exact workspace/accepted-head verification, index lag, changed Git
bytes, cross-workspace isolation, and file-limit failure. This source review
slice does not complete candidate security acceptance.
