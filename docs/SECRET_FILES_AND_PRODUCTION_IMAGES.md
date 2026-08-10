# Secret-file injection and production-image plan

Status: accepted `0.1.3` deployment plan. Implementation remains assigned to `TD-RISK-004` and `TD-RISK-007` in `docs/ENGINEERING_RISKS.md`.

## Current boundary

The local Compose profile supplies generated development values as environment variables and deliberately permits localhost HTTP and Mailpit SMTP. This is not the supported long-term production secret boundary. The production-target image now receives an isolated smoke rehearsal, but web startup still applies migrations and the default operator profile still needs later runtime hardening.

## Secret-file contract

`0.3.1` will add a single configuration reader for sensitive settings. Each supported secret will accept either its existing variable or a mutually exclusive `<NAME>_FILE` path. Supplying both, neither where required, an empty/oversized file, a directory, a symlink outside the approved secret mount, or a file readable by unintended users will fail startup without printing the value or file contents.

The initial file-backed set is:

- `DJANGO_SECRET_KEY_FILE`;
- `POSTGRES_PASSWORD_FILE`;
- `TEKDOCS_MASTER_KEY_FILE`;
- `TEKDOCS_PUBLICATION_SIGNING_KEY_FILE`;
- `TEKDOCS_BOOTSTRAP_TOKEN_FILE`;
- `EMAIL_HOST_PASSWORD_FILE` when SMTP authentication is enabled;
- `TEKDOCS_OIDC_CLIENT_SECRET_FILE` when OIDC is enabled.

Docker Compose will mount individual secrets read-only below `/run/secrets`; Kubernetes-compatible deployments may project the same files. Secret values and resolved paths remain excluded from health responses, logs, audits, task arguments, image layers, support bundles, and browser configuration. Development may retain explicit environment values, while the supported production profile will require files by `0.8.7`.

Rotation tests will distinguish reloadable connection credentials from process-start keys. MFA wrapping-key rotation will rewrap protected MFA material before the old key is retired. Django signing-key and publication-key rotation will retain documented verification/rollback windows. Removing the bootstrap token after the one-time claim must not make an already bootstrapped installation fail to start. The `0.3.2` slice implements this file-input contract; customer credential references delivered in `0.3.1` are not deployment secrets and never grant TekDocs access to provider values.

## Exact production-image testing

`make production-image-rehearsal` builds the backend, worker, and scheduler from the Dockerfile `production` target in a uniquely named Compose project with new volumes and generated ephemeral settings. It verifies proxy-to-backend readiness, completed migrations, absence of pytest from the runtime image, and the unprivileged runtime user. The rehearsal never reuses the ordinary development database.

Before beta, migrations move to an explicit one-shot deployment job; web and worker replicas start only after that job succeeds. `0.8.7` will also verify read-only filesystems where practical, dropped capabilities, resource limits, graceful shutdown, proxy/TLS behavior, and digest-pinned runtime bases. `0.9.4` will execute the same smoke contract against the exact signed release digest and retain its SBOM/provenance evidence.

## Failure and ownership

Configuration parsing and production-image startup are release-blocking. A failed secret read, ambiguous source, migration, health check, or runtime-user assertion must stop deployment rather than fall back silently. Backend maintainers own the configuration reader and cryptographic rotation tests; deployment maintainers own secret mounts, migration jobs, and image policy; release evidence must demonstrate both sides together.
