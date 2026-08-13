# Upgrade and rollback operations

TekDocs supports direct forward upgrades from the retained stabilization release of every prior `0.x` line: `0.1.3`, `0.2.9`, `0.3.12`, `0.4.9`, `0.5.9`, `0.6.9`, `0.7.13`, and `0.8.0`. Intermediate development slices are not separate production support baselines.

## Before upgrading

1. Read every release note after the installed version and retain the current checkout, environment file, Compose overlays, and image digests.
2. Generate or retrieve the separately custodied recovery key.
3. While the old stack is healthy, use the new checkout's `scripts/tekdocs-backup.sh` to create an encrypted pre-upgrade recovery set. The helper image comes from the new checkout, while PostgreSQL and media are captured from the running old project.
4. Copy the complete set off host and run a restore into an independently named project. Do not use the production project as the first restore test.
5. Verify free space, PostgreSQL health, managed-media access, outgoing mail/storage dependencies, and the exact Compose project name.

The automated supported matrix uses real PostgreSQL, the one-shot migration owner, constrained runtime role, and domain-specific retained fixtures:

```sh
make supported-upgrade-matrix
```

## Forward upgrade

Stop application traffic, retain the database/media volumes, and apply the new checkout with the same environment and secret files. The migration service must complete before application services start. Require `backend`, `worker`, `scheduler`, and `frontend` health, then verify authentication, exact client Workspace isolation, one retained STATIC publication, attachment access, inventory/network records, notification state, integration state, and compliance/monitoring evidence appropriate to the installation.

Never grant the runtime role schema-owner or `BYPASSRLS` privileges to make an upgrade pass. Never delete volumes to clear a migration failure.

## Failure and rollback

Django migration reversal is not the production rollback mechanism. A later schema may be forward-only, and an older application is not assumed compatible with a database already touched by newer migrations.

If failure occurs before migrations begin, stop the attempted stack and restart the retained old images and configuration against the untouched volumes. If a migration starts, its result is uncertain, or new application writes occur, stop all new-version processes and perform a full recovery:

1. preserve failure logs without secret values;
2. use the retained old checkout/images as the target application version;
3. invoke the supported restore with the pre-upgrade recovery set and exact old Compose project confirmation;
4. supply recovered deployment secrets through the old deployment's expected custody boundary;
5. start the old release, verify health and retained sentinels, and keep the failed volumes isolated until incident review completes.

Restoring necessarily discards writes made after the pre-upgrade backup. Operators must communicate and record that recovery point. Do not improvise table-level copies, manually edit Django migration history, or partially reuse post-failure media volumes.

## Evidence and support policy

The matrix pins source commits and first verifies each source's checked-in `VERSION`. Each case creates meaningful state at that source, applies the current tree, and verifies identities, retained bytes, signatures, policy/RLS startup, migrations, and domain invariants. Failure of any supported source blocks release.

The matrix does not certify a distribution-specific Docker/kernel/storage stack or future downgrade. Clean-install, encrypted recovery, backup/restore, browser, and production-image rehearsals remain separate gates.
