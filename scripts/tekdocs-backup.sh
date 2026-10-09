#!/bin/sh
set -eu

#=======================# TekDocs Encrypted Backup #=======================#
#
# Capture one authenticated recovery set while application writers are paused.
# PostgreSQL, managed media, every managed Git repository, and deployment
# secrets are encrypted independently and bound by one authenticated manifest.

#=======================# VARIABLES #=======================#

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
. "$repository_root/scripts/lib/recovery-checksum.sh"
environment_file=.env
secret_directory=
output_directory=
key_file=
paused_services=
repository_helper=
repository_archive_path=

#======================# FUNCTIONS #=======================#

usage() {
  echo "Usage: $0 --output DIRECTORY --key-file FILE --secret-directory DIRECTORY [--env-file FILE]" >&2
  exit 2
}
backup_compose() {
  TEKDOCS_SECRET_DIRECTORY="$absolute_secrets" docker compose --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.production.yml" \
    -f "$repository_root/compose.secret-files.yml" -f "$repository_root/compose.bootstrap-secret.yml" "$@"
}
resume_services() {
  [ -n "$paused_services" ] || return 0
  # shellcheck disable=SC2086
  backup_compose start $paused_services >/dev/null
  paused_services=
}
cleanup() {
  status=$?
  if [ -n "$repository_helper" ]; then
    if [ -n "$repository_archive_path" ]; then
      docker run --rm --volumes-from "$repository_helper" --entrypoint rm \
        "$backend_image" -f "$repository_archive_path" >/dev/null 2>&1 || true
    fi
    docker rm -f "$repository_helper" >/dev/null 2>&1 || true
  fi
  resume_services || true
  rm -rf "$partial_directory"
  exit "$status"
}
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

#=========================# MAIN #==========================#

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

backend_id=$(backup_compose ps -q backend)
db_id=$(backup_compose ps -q db)
[ -n "$backend_id" ] && [ -n "$db_id" ] || {
  echo "TekDocs backend and database services must already be running." >&2
  exit 1
}
backend_image=$(docker inspect --format '{{.Image}}' "$backend_id")
[ -n "$backend_image" ] || { echo "The running backend image could not be resolved." >&2; exit 1; }
media_volume=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Name}}{{end}}{{end}}' "$backend_id")
[ -n "$media_volume" ] || { echo "The managed media volume could not be resolved." >&2; exit 1; }

partial_directory="${output_directory}.partial.$$"
umask 077
mkdir -m 0700 "$partial_directory"
trap cleanup EXIT HUP INT TERM

for service in frontend scheduler worker backend; do
  if backup_compose ps --status running --services | grep -qx "$service"; then
    paused_services="$paused_services $service"
  fi
done
if [ -n "$paused_services" ]; then
  echo "Pausing TekDocs writers for a consistent recovery snapshot"
  # shellcheck disable=SC2086
  backup_compose stop $paused_services >/dev/null
fi

echo "Capturing PostgreSQL into an authenticated encrypted artifact"
database_pipe="$partial_directory/database.pipe"
mkfifo "$database_pipe"
crypto_encrypt database < "$database_pipe" > "$partial_directory/database.tdr" &
database_crypto_pid=$!
if ! backup_compose exec -T db sh -c \
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

echo "Capturing managed repositories as verified Git bundles"
project_name=$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' "$environment_file" | head -n 1)
project_name=${project_name:-tekdocs}
repository_helper="${project_name}-repository-backup-$$"
repository_archive_path="/app/repositories/.tekdocs-recovery-$$.tar"
if ! backup_compose run --name "$repository_helper" --no-deps backend \
  python manage.py repository_recovery create --archive "$repository_archive_path" >/dev/null; then
  echo "Managed-repository backup capture failed." >&2
  exit 1
fi
if ! docker run --rm --volumes-from "$repository_helper":ro --entrypoint python \
  --user 0:0 \
  -v "$absolute_key:/run/secrets/recovery_key:ro" \
  "$backend_image" -m tekdocs.recovery_archive encrypt \
  --key-file /run/secrets/recovery_key --label repositories --input "$repository_archive_path" \
  > "$partial_directory/repositories.tdr"; then
  echo "Managed-repository encryption failed." >&2
  exit 1
fi
docker run --rm --volumes-from "$repository_helper" --entrypoint rm \
  "$backend_image" -f "$repository_archive_path"
repository_archive_path=
docker rm "$repository_helper" >/dev/null
repository_helper=

resume_services

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

database_sha=$(recovery_sha256 "$partial_directory/database.tdr")
media_sha=$(recovery_sha256 "$partial_directory/media.tdr")
secrets_sha=$(recovery_sha256 "$partial_directory/deployment-secrets.tdr")
repositories_sha=$(recovery_sha256 "$partial_directory/repositories.tdr")
created_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
version=$(tr -d '[:space:]' < "$repository_root/VERSION")
printf '%s\n' \
  '{' \
  '  "format": "tekdocs-recovery-v2",' \
  "  \"tekdocs_version\": \"$version\"," \
  "  \"created_at\": \"$created_at\"," \
  '  "artifacts": {' \
  "    \"database.tdr\": \"$database_sha\"," \
  "    \"media.tdr\": \"$media_sha\"," \
  "    \"deployment-secrets.tdr\": \"$secrets_sha\"," \
  "    \"repositories.tdr\": \"$repositories_sha\"" \
  '  }' \
  '}' > "$partial_directory/manifest.json"
crypto_manifest_mac > "$partial_directory/manifest.mac"
chmod 0600 "$partial_directory"/*
mv "$partial_directory" "$output_directory"
trap - EXIT HUP INT TERM
echo "Encrypted TekDocs recovery set created at $output_directory"
