# Operator-owned 1Password runtime injection

This optional workflow uses 1Password CLI on the deployment host to materialize TekDocs runtime files. It does **not** integrate TekDocs with the 1Password API. The CLI session and any service-account token remain in the operator boundary; application containers receive only service-scoped Docker secret mounts.

1Password documents `op read` and `op inject` for loading secret references into scripts/configuration and recommends a least-privilege service account for unattended automation. Review the current upstream guidance before adopting unattended access: [Load secrets into scripts](https://developer.1password.com/docs/cli/secrets-scripts).

## Prepare custody

1. Create a dedicated 1Password deployment vault and item rather than using customer credential vaults.
2. Grant the human operator or deployment-only service account read access only to that vault.
3. Install and authenticate 1Password CLI on the host. Do not install it in a TekDocs image.
4. Copy `.env.production.example` to a root-owned file outside the repository and set only non-secret deployment configuration plus `TEKDOCS_SECRET_DIRECTORY=/run/tekdocs-secrets`.
5. Keep the 1Password secret-reference mapping outside the repository with mode `0600`. A mapping needs one reference for each required filename:

```text
django_secret_key=<operator-owned 1Password secret reference>
postgres_owner_password=<operator-owned 1Password secret reference>
postgres_runtime_password=<operator-owned 1Password secret reference>
tekdocs_master_key=<operator-owned 1Password secret reference>
publication_signing_key=<operator-owned 1Password secret reference>
bootstrap_token=<operator-owned 1Password secret reference>
```

Add `email_host_password` and `oidc_client_secret` only when those features are configured. Secret references identify deployment fields; they are metadata and must still be protected from logs, tickets, and source control.

## Materialize files

Run the following as the deployment operator from a protected host session. `/run` is normally memory-backed; confirm that property on the target operating system. The allowlist prevents the mapping from choosing arbitrary output paths.

```sh
install -d -m 0700 /run/tekdocs-secrets
umask 077
while IFS='=' read -r filename reference; do
  case "$filename" in
    django_secret_key|postgres_owner_password|postgres_runtime_password|tekdocs_master_key|publication_signing_key|bootstrap_token|email_host_password|oidc_client_secret) ;;
    *) echo "Rejected unknown TekDocs secret filename" >&2; exit 1 ;;
  esac
  temporary_file=$(mktemp "/run/tekdocs-secrets/${filename}.XXXXXX")
  if ! op read "$reference" > "$temporary_file"; then
    rm -f "$temporary_file"
    exit 1
  fi
  if [ ! -s "$temporary_file" ]; then
    rm -f "$temporary_file"
    exit 1
  fi
  chmod 0600 "$temporary_file"
  mv "$temporary_file" "/run/tekdocs-secrets/$filename"
done < /root/tekdocs-1password-references
```

Do not enable shell tracing. Never pass a 1Password account password, CLI session, `OP_SERVICE_ACCOUNT_TOKEN`, Connect token, or secret reference through Compose. In particular, do not wrap `docker compose` in `op run`; that could copy operator credentials into subprocess environments.

## Start and retire bootstrap custody

For the first start, include the one-time bootstrap overlay:

```sh
docker compose --env-file /etc/tekdocs/production.env \
  -f compose.yml \
  -f compose.production.yml \
  -f compose.secret-files.yml \
  -f compose.bootstrap-secret.yml \
  up -d --build --wait
```

Add `-f compose.smtp-secret.yml` when authenticated SMTP is configured and `-f compose.oidc-secret.yml` when OIDC is configured. After the first owner is successfully created, recreate the stack without `compose.bootstrap-secret.yml`, then remove `/run/tekdocs-secrets/bootstrap_token`. Readiness will remain healthy because the immutable database state records that bootstrap is closed.

## Rotation and restart

Materialize changed values into temporary files and atomically rename them as above, then recreate the affected services. TekDocs does not hot-reload process-start secrets. Database, Django signing, MFA wrapping, and publication-signing changes require their domain-specific continuity procedure; replacing those files alone can cause outage or loss of access. This recipe is injection plumbing, not automated safe rotation or backup.

If a service account is used, keep its token in the host's own secret manager or service manager credential facility. TekDocs must never be the process that holds or uses it.
