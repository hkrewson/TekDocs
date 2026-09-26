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
