#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
environment_file=.env
backup_directory=
key_file=
secret_output=
confirmation=

usage() {
  echo "Usage: $0 --backup DIRECTORY --key-file FILE --secret-output DIRECTORY --confirm-destroy PROJECT [--env-file FILE]" >&2
  exit 2
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --backup) backup_directory=${2:-}; shift 2 ;;
    --key-file) key_file=${2:-}; shift 2 ;;
    --secret-output) secret_output=${2:-}; shift 2 ;;
    --confirm-destroy) confirmation=${2:-}; shift 2 ;;
    --env-file) environment_file=${2:-}; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$backup_directory" ] && [ -n "$key_file" ] && [ -n "$secret_output" ] || usage
[ -d "$backup_directory" ] && [ -f "$key_file" ] && [ -f "$environment_file" ] || usage
project_name=$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' "$environment_file" | head -n 1)
project_name=${project_name:-tekdocs}
[ "$confirmation" = "$project_name" ] || {
  echo "Restore is destructive. Pass --confirm-destroy $project_name to replace its database and managed media volumes." >&2
  exit 1
}
[ ! -e "$secret_output" ] || { echo "Refusing to overwrite an existing secret-output path." >&2; exit 1; }

for artifact in manifest.json manifest.mac database.tdr media.tdr deployment-secrets.tdr; do
  [ -f "$backup_directory/$artifact" ] || { echo "The recovery set is incomplete." >&2; exit 1; }
done
absolute_backup=$(CDPATH= cd -- "$backup_directory" && pwd)
absolute_key=$(CDPATH= cd -- "$(dirname "$key_file")" && pwd)/$(basename "$key_file")
absolute_secret_parent=$(CDPATH= cd -- "$(dirname "$secret_output")" && pwd)
secret_output="$absolute_secret_parent/$(basename "$secret_output")"
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-supported-restore.XXXXXX")
chmod 0700 "$work_directory"
cleanup() { rm -rf "$work_directory"; }
trap cleanup EXIT HUP INT TERM

backend_image=$(docker build --quiet "$repository_root/backend")
[ -n "$backend_image" ] || { echo "The recovery helper image is unavailable." >&2; exit 1; }
crypto() {
  docker run --rm --entrypoint python \
    --user "$(id -u):$(id -g)" \
    -v "$absolute_key:/run/secrets/recovery_key:ro" \
    -v "$absolute_backup:/recovery:ro" \
    -v "$work_directory:/work" \
    "$backend_image" -m tekdocs.recovery_archive "$@" --key-file /run/secrets/recovery_key
}

expected_mac=$(tr -d '[:space:]' < "$absolute_backup/manifest.mac")
crypto verify-manifest --input /recovery/manifest.json --expected-mac "$expected_mac"
grep -q '"format": "tekdocs-recovery-v1"' "$absolute_backup/manifest.json"
for artifact in database.tdr media.tdr deployment-secrets.tdr; do
  expected=$(sed -n "s/.*\"$artifact\": \"\([0-9a-f]\{64\}\)\".*/\1/p" "$absolute_backup/manifest.json")
  actual=$(sha256sum "$absolute_backup/$artifact" | awk '{print $1}')
  [ -n "$expected" ] && [ "$expected" = "$actual" ] || { echo "Recovery artifact checksum validation failed." >&2; exit 1; }
done

echo "Authenticating recovery artifacts before destructive changes"
crypto decrypt --label database --input /recovery/database.tdr --output /work/database.dump
crypto decrypt --label media --input /recovery/media.tdr --output /work/media.tar
crypto decrypt --label deployment-secrets --input /recovery/deployment-secrets.tdr --output /work/deployment-secrets.tar
tar -tf "$work_directory/deployment-secrets.tar" > "$work_directory/secret-members"
if grep -Ev '^(django_secret_key|postgres_owner_password|postgres_runtime_password|tekdocs_master_key|publication_signing_key|bootstrap_token|email_host_password|oidc_client_secret)$' "$work_directory/secret-members" | grep -q .; then
  echo "The encrypted secret archive contains an unexpected path." >&2
  exit 1
fi
for required_secret in django_secret_key postgres_owner_password postgres_runtime_password tekdocs_master_key publication_signing_key; do
  grep -qx "$required_secret" "$work_directory/secret-members" || { echo "The encrypted secret archive is incomplete." >&2; exit 1; }
done
mkdir -m 0700 "$secret_output"
tar -xf "$work_directory/deployment-secrets.tar" -C "$secret_output"
chmod 0600 "$secret_output"/*

export TEKDOCS_SECRET_DIRECTORY="$secret_output"
restore_compose() {
  docker compose --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.production.yml" \
    -f "$repository_root/compose.secret-files.yml" -f "$repository_root/compose.bootstrap-secret.yml" "$@"
}

echo "Replacing only the explicitly confirmed TekDocs project volumes"
restore_compose down --volumes --remove-orphans
restore_compose up -d --wait db mailpit
restore_compose exec -T db sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --clean --if-exists' \
  < "$work_directory/database.dump"
restore_compose run --rm migrate
restore_compose create backend >/dev/null
backend_id=$(restore_compose ps -q --all backend)
media_volume=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Name}}{{end}}{{end}}' "$backend_id")
[ -n "$media_volume" ] || { echo "The restored media volume could not be resolved." >&2; exit 1; }
docker run --rm -i -v "$media_volume:/restore" \
  postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193 \
  tar -xf - -C /restore < "$work_directory/media.tar"
restore_compose up -d --wait
restore_compose exec -T backend python manage.py check
echo "TekDocs recovery completed for explicitly confirmed project $project_name"
