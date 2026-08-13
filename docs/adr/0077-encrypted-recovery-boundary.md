# ADR 0077: Authenticated, key-separated recovery boundary

Date: 2026-08-13

Status: Accepted for `0.8.1`

## Decision

The supported backup is an atomic recovery set containing PostgreSQL, managed media, and an allowlisted archive of deployment keys. Each stream is encrypted independently with AES-256-GCM using a random nonce and artifact-specific associated data. A separate operator-held 256-bit recovery key authenticates both artifacts and the plaintext metadata manifest; it is never stored in PostgreSQL, Compose, a TekDocs volume, or the deployment-secret directory.

Backup streams producers through private FIFOs into encryption so database, media, and secret archives are not staged as plaintext. Producer and encryptor status must both succeed before the partial directory is atomically promoted. Restore authenticates and decrypts every artifact into a mode-`0700` temporary directory before destructive work. It then requires an exact Compose-project confirmation, replaces only that project's database and media volumes, provisions current runtime-role grants after `pg_restore --no-privileges`, runs migrations, and requires application health.

Recovery diagnostics never disclose key values, ciphertext, database content, media names, secret values, or host secret paths. The restore refuses unexpected archive members, existing secret-output paths, incomplete sets, modified manifests, checksum mismatches, wrong keys, and missing destructive confirmation.

## Consequences

An attacker who acquires only the recovery set cannot decrypt it. An attacker who controls both the set and recovery key can recover all backed-up application and deployment material; custody and off-host retention remain operator responsibilities. Loss of the recovery key and live deployment keys is intentionally unrecoverable. This slice provides operator-invoked full recovery, not online point-in-time recovery, scheduling, remote storage transport, or a claim that an untested copy is a valid backup. Those recurring exercises remain `0.9.3` work.
