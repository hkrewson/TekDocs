# Secret-file injection and production-image contract

Status: production file-only enforcement and local container hardening are certified in `0.8.7`; exact signed published-image evidence remains `0.9.4`.

## Configuration sources

Each supported sensitive setting accepts either its existing variable or a mutually exclusive `<NAME>_FILE` path. A non-empty direct value and a file source together fail startup. An empty variable emitted by Compose is treated as absent, which permits the file overlay to replace development-oriented environment keys.

The file-backed set is:

- `DJANGO_SECRET_KEY_FILE`;
- `POSTGRES_PASSWORD_FILE` for either the database owner or runtime connection, depending on the service;
- `TEKDOCS_DATABASE_RUNTIME_PASSWORD_FILE` for the migration service's role provisioning;
- `TEKDOCS_MASTER_KEY_FILE`;
- `TEKDOCS_PUBLICATION_SIGNING_KEY_FILE`;
- `TEKDOCS_BOOTSTRAP_TOKEN_FILE` before the first-owner claim;
- `EMAIL_HOST_PASSWORD_FILE` when authenticated SMTP is enabled;
- `TEKDOCS_OIDC_CLIENT_SECRET_FILE` when OIDC is enabled.

Files must use an absolute path, resolve beneath `TEKDOCS_SECRET_ROOT` (default `/run/secrets`), identify a regular file owned by root or the application user, be no larger than 4 KiB, and contain one printable UTF-8 value with at most one terminal newline. Relative paths, outside-root or escaping symlinks, directories, missing/empty/oversized/non-UTF-8/multiline values, outer whitespace, unexpected ownership, and group/other write or execute permission fail closed. Outside Docker's service-scoped `/run/secrets` mount, group/other read permission also fails. Diagnostics name only the setting and violated rule; they never include the value or configured host path.

## Compose overlays

`compose.secret-files.yml` supplies the required long-lived files. It gives the database only its owner password, the migration job the owner/runtime database credentials plus process keys, and web/worker/scheduler only the runtime database credential plus process keys.

`compose.smtp-secret.yml` and `compose.oidc-secret.yml` are independent optional overlays for authenticated SMTP and OIDC. `compose.bootstrap-secret.yml` is added only until the first owner is created. After that successful claim, remove the bootstrap overlay and source file; readiness deliberately permits a bootstrapped installation without the token while failing an unclaimed installation that lacks it.

Use `.env.production.example` as the non-secret environment starting point. The `TEKDOCS_SECRET_DIRECTORY` source should be an absolute, root-owned runtime directory outside the repository, preferably on host tmpfs such as `/run/tekdocs-secrets`. Source files should be mode `0600`; Compose exposes them read-only and only to the named service under `/run/secrets`.

Development may continue to use `make bootstrap` and direct values in the ignored `.env`. The supported production overlay sets `TEKDOCS_REQUIRE_SECRET_FILES=true`; required direct or missing application secret sources fail startup. Configured SMTP and OIDC credentials also require their file overlays.

## Rotation boundaries

- Database passwords require coordinated database-role and service restart handling; they are not hot-reloaded.
- `DJANGO_SECRET_KEY`, the MFA wrapping key, and the publication signing key are process-start values. Changing them without their separately documented continuity/rewrap procedure can invalidate sessions, MFA material, or publication expectations.
- SMTP and OIDC secrets take effect after service recreation.
- The bootstrap token can be removed, rather than rotated, after the immutable database claim closes first-owner setup.

Automated rotation and key-loss recovery remain later operational work. `0.3.2` establishes safe injection and explicit process boundaries; it does not claim zero-downtime rotation.

## Production-image evidence

`make production-image-rehearsal` builds the migration, backend, worker, and scheduler from the Dockerfile `production` target in a unique Compose project with fresh volumes and generated file-only secrets. It verifies:

- completed migrations and proxy-to-backend readiness;
- healthy web, worker, scheduler, PostgreSQL, Valkey, Mailpit, and frontend services;
- no pytest in the runtime image and an unprivileged backend user;
- least-scope service mounts;
- no secret values in container environments, image history, or combined service logs;
- no host secret-directory path in service logs;
- fail-closed direct-plus-file ambiguity without value/path disclosure.
- read-only application roots, explicit tmpfs writes, dropped capabilities, `no-new-privileges`, process ceilings, and structured request evidence.

The rehearsal never reuses the ordinary development database. TLS termination remains the deployment proxy's responsibility. `0.9.4` will run the smoke contract against the exact signed release digest and retain SBOM/provenance evidence.

## Custody boundary

Runtime deployment secrets are distinct from customer credential references. The operator may materialize runtime files from 1Password, another secret manager, or an offline process, but TekDocs receives only the mounted results. No 1Password session, service-account token, Connect token, vault reference, CLI binary, or retrieval permission enters the application containers. See `docs/ONEPASSWORD_RUNTIME_INJECTION.md` for the operator workflow.
