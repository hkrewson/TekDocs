#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
environment_file=.env
secret_directory=
output_directory=
key_file=

usage() {
  echo "Usage: $0 --output DIRECTORY --key-file FILE --secret-directory DIRECTORY [--env-file FILE]" >&2
  exit 2
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output_directory=${2:-}; shift 2 ;;
    --key-file) key_file=${2:-}; shift 2 ;;
    --secret-directory) secret_directory=${2:-}; shift 2 ;;
    --env-file) environment_file=${2:-}; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$output_directory" ] && [ -n "$key_file" ] && [ -n "$secret_directory" ] || usage
[ -f "$environment_file" ] && [ -f "$key_file" ] && [ -d "$secret_directory" ] || usage

absolute_key=$(CDPATH= cd -- "$(dirname "$key_file")" && pwd)/$(basename "$key_file")
absolute_secrets=$(CDPATH= cd -- "$secret_directory" && pwd)
case "$absolute_key" in "$absolute_secrets"/*) echo "The recovery key must not be stored with deployment secrets." >&2; exit 1 ;; esac
if [ -e "$output_directory" ]; then
  echo "Refusing to overwrite an existing backup path." >&2
  exit 1
fi

for required_secret in django_secret_key postgres_owner_password postgres_runtime_password tekdocs_master_key publication_signing_key; do
  [ -f "$absolute_secrets/$required_secret" ] || {
    echo "The production secret set is incomplete." >&2
    exit 1
  }
done
for direct_name in DJANGO_SECRET_KEY POSTGRES_OWNER_PASSWORD POSTGRES_RUNTIME_PASSWORD TEKDOCS_MASTER_KEY TEKDOCS_PUBLICATION_SIGNING_KEY; do
  direct_value=$(sed -n "s/^${direct_name}=//p" "$environment_file" | head -n 1)
  [ -z "$direct_value" ] || {
    echo "Supported backups require the production file-only secret profile." >&2
    exit 1
  }
done

backend_id=$(docker compose --env-file "$environment_file" ps -q backend)
db_id=$(docker compose --env-file "$environment_file" ps -q db)
[ -n "$backend_id" ] && [ -n "$db_id" ] || {
  echo "TekDocs backend and database services must already be running." >&2
  exit 1
}
backend_image=$(docker inspect --format '{{.Image}}' "$backend_id")
media_volume=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Name}}{{end}}{{end}}' "$backend_id")
[ -n "$media_volume" ] || { echo "The managed media volume could not be resolved." >&2; exit 1; }

partial_directory="${output_directory}.partial.$$"
umask 077
mkdir -m 0700 "$partial_directory"
cleanup() { rm -rf "$partial_directory"; }
trap cleanup EXIT HUP INT TERM

crypto_encrypt() {
  label=$1
  docker run --rm -i --entrypoint python \
    --user "$(id -u):$(id -g)" \
    -v "$absolute_key:/run/secrets/recovery_key:ro" \
    "$backend_image" -m tekdocs.recovery_archive encrypt \
    --key-file /run/secrets/recovery_key --label "$label"
}
crypto_manifest_mac() {
  docker run --rm --entrypoint python \
    --user "$(id -u):$(id -g)" \
    -v "$absolute_key:/run/secrets/recovery_key:ro" \
    -v "$partial_directory:/recovery:ro" \
    "$backend_image" -m tekdocs.recovery_archive manifest-mac \
    --key-file /run/secrets/recovery_key --input /recovery/manifest.json
}

echo "Capturing PostgreSQL into an authenticated encrypted artifact"
database_pipe="$partial_directory/database.pipe"
mkfifo "$database_pipe"
crypto_encrypt database < "$database_pipe" > "$partial_directory/database.tdr" &
database_crypto_pid=$!
if ! docker compose --env-file "$environment_file" exec -T db sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges' \
  > "$database_pipe"; then
  wait "$database_crypto_pid" || true
  echo "PostgreSQL backup capture failed." >&2
  exit 1
fi
wait "$database_crypto_pid"
rm -f "$database_pipe"

echo "Capturing managed media into an authenticated encrypted artifact"
media_pipe="$partial_directory/media.pipe"
mkfifo "$media_pipe"
crypto_encrypt media < "$media_pipe" > "$partial_directory/media.tdr" &
media_crypto_pid=$!
if ! docker run --rm -i -v "$media_volume:/source:ro" \
  postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193 \
  tar -cf - -C /source . > "$media_pipe"; then
  wait "$media_crypto_pid" || true
  echo "Managed-media backup capture failed." >&2
  exit 1
fi
wait "$media_crypto_pid"
rm -f "$media_pipe"

secret_names="django_secret_key postgres_owner_password postgres_runtime_password tekdocs_master_key publication_signing_key"
for optional_secret in bootstrap_token email_host_password oidc_client_secret; do
  if [ -f "$absolute_secrets/$optional_secret" ]; then secret_names="$secret_names $optional_secret"; fi
done
echo "Capturing required deployment keys into the encrypted recovery set"
secrets_pipe="$partial_directory/deployment-secrets.pipe"
mkfifo "$secrets_pipe"
crypto_encrypt deployment-secrets < "$secrets_pipe" > "$partial_directory/deployment-secrets.tdr" &
secrets_crypto_pid=$!
# shellcheck disable=SC2086
if ! tar -cf - -C "$absolute_secrets" $secret_names > "$secrets_pipe"; then
  wait "$secrets_crypto_pid" || true
  echo "Deployment-secret backup capture failed." >&2
  exit 1
fi
wait "$secrets_crypto_pid"
rm -f "$secrets_pipe"

database_sha=$(sha256sum "$partial_directory/database.tdr" | awk '{print $1}')
media_sha=$(sha256sum "$partial_directory/media.tdr" | awk '{print $1}')
secrets_sha=$(sha256sum "$partial_directory/deployment-secrets.tdr" | awk '{print $1}')
created_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
version=$(tr -d '[:space:]' < "$repository_root/VERSION")
printf '%s\n' \
  '{' \
  '  "format": "tekdocs-recovery-v1",' \
  "  \"tekdocs_version\": \"$version\"," \
  "  \"created_at\": \"$created_at\"," \
  '  "artifacts": {' \
  "    \"database.tdr\": \"$database_sha\"," \
  "    \"media.tdr\": \"$media_sha\"," \
  "    \"deployment-secrets.tdr\": \"$secrets_sha\"" \
  '  }' \
  '}' > "$partial_directory/manifest.json"
crypto_manifest_mac > "$partial_directory/manifest.mac"
chmod 0600 "$partial_directory"/*
mv "$partial_directory" "$output_directory"
trap - EXIT HUP INT TERM
echo "Encrypted TekDocs recovery set created at $output_directory"
