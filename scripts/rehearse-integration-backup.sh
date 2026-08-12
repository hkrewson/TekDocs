#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-integration-backup.XXXXXX")
environment_file="$work_directory/recovery.env"
backup_directory="$work_directory/backup"
source_project="tekdocs_integration_backup_$$"
restore_project="tekdocs_integration_restore_$$"
fixture_password=$(openssl rand -base64 36 | tr -d '\n')
provider_token=$(openssl rand -base64 48 | tr -d '\n')
mkdir -p "$backup_directory"

compose_for() {
  project_name=$1
  shift
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}
cleanup() {
  compose_for "$source_project" down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  compose_for "$restore_project" down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$environment_file"
compose_for "$source_project" up -d --build --wait backend
compose_for "$source_project" exec -T -e TEKDOCS_FIXTURE_MODE=create -e TEKDOCS_FIXTURE_PASSWORD="$fixture_password" \
  -e TEKDOCS_FIXTURE_PROVIDER_TOKEN="$provider_token" backend python manage.py shell \
  < "$repository_root/scripts/integration-runtime-fixture.py"
compose_for "$source_project" exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$backup_directory/postgres.dump"
docker run --rm -v "${source_project}_media_data:/source:ro" -v "$backup_directory:/backup" \
  postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193 \
  tar -czf /backup/media.tar.gz -C /source .
test -s "$backup_directory/postgres.dump"
test -s "$backup_directory/media.tar.gz"
compose_for "$source_project" down --volumes --remove-orphans

compose_for "$restore_project" up -d --wait db
compose_for "$restore_project" run --rm migrate
compose_for "$restore_project" exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < "$backup_directory/postgres.dump"
compose_for "$restore_project" create backend >/dev/null
docker run --rm -v "${restore_project}_media_data:/restore" -v "$backup_directory:/backup:ro" \
  postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193 \
  tar -xzf /backup/media.tar.gz -C /restore
compose_for "$restore_project" up -d --build --wait backend worker scheduler
compose_for "$restore_project" exec -T -e TEKDOCS_FIXTURE_MODE=verify \
  -e TEKDOCS_FIXTURE_PROVIDER_TOKEN="$provider_token" backend python manage.py shell \
  < "$repository_root/scripts/integration-runtime-fixture.py"
compose_for "$restore_project" exec -T backend python manage.py check
echo "Integration backup/restore rehearsal passed"
