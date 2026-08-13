# Encrypted backup and recovery

TekDocs `0.8.1` supports a self-contained encrypted recovery set for PostgreSQL, managed media, and the deployment keys required to read retained encrypted/signature material. The recovery key is deliberately separate from both TekDocs and its deployment-secret directory.

## Custody model

Generate a 256-bit recovery key on an operator-controlled system:

```sh
./scripts/generate-recovery-key.sh /secure/off-host/tekdocs-recovery.key
```

The command creates a new mode-`0600` file and refuses to overwrite an existing path. Keep at least two tested copies under separate administrative custody. Do not place this file in the repository, the Compose secret directory, a TekDocs volume, a ticket, or an ordinary synchronized folder. Losing both the recovery key and the live deployment keys makes the encrypted recovery set unusable by design.

## Backup

Run the supported production file-secret profile first. With its backend and database healthy:

```sh
./scripts/tekdocs-backup.sh \
  --env-file .env.production \
  --secret-directory /run/operator/tekdocs-secrets \
  --key-file /secure/off-host/tekdocs-recovery.key \
  --output /backups/tekdocs/2026-08-13T060000Z
```

The output directory is created atomically and never overwritten. It contains authenticated AES-256-GCM database, media, and deployment-key artifacts plus a non-secret manifest, SHA-256 transport checksums, and an HMAC over that manifest. No plaintext database, media, or key archive is written to the host. A producer or encryption failure aborts the set.

Copy each complete set to independently protected remote storage. Automation should alert on command failure, retain immutable generations according to local policy, and run the rehearsal below after changes. A backup is not proven until it restores.

## Restore

Recovery replaces the database and managed-media volumes for exactly the Compose project named in the supplied environment file. It refuses an existing secret-output directory and requires an exact destructive confirmation:

```sh
./scripts/tekdocs-restore.sh \
  --env-file .env.production \
  --backup /backups/tekdocs/2026-08-13T060000Z \
  --key-file /secure/off-host/tekdocs-recovery.key \
  --secret-output /run/operator/restored-tekdocs-secrets \
  --confirm-destroy tekdocs
```

Before changing volumes, the command authenticates the manifest, validates every artifact checksum, decrypts all three artifacts into a private temporary directory, and validates the secret archive allowlist. Only then does it remove the explicitly confirmed project's volumes, restore PostgreSQL and media, reapply runtime-role privileges, run migrations, and require the production stack to become healthy.

Treat the recovered secret directory as production material. Verify application access and retained publications/evidence, then move it into the deployment's normal secret-file custody. A failed authentication message is intentionally value-free; it can mean the wrong key or modified/corrupt ciphertext. Do not bypass it.

## Rehearsal and limitations

Run the isolated production-target proof with:

```sh
make supported-recovery-rehearsal
```

It creates representative signed and encrypted application state, proves plaintext is absent from the recovery set, rejects missing confirmation and a wrong key before destructive work, restores into independently named volumes, and verifies retained state and deployment keys.

This initial supported workflow is operator-invoked and local-volume oriented. Scheduling, remote retention adapters, media/database point-in-time recovery, deliberate lost-key exercises, and recurring disaster-recovery evidence remain release-candidate work in `0.9.3`.
