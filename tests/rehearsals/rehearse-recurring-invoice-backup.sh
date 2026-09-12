#!/bin/sh

#=======================# Recurring invoice recovery #=======================#
# Restore a separate stack from a database/media backup, retaining approved
# billing identities and verifying runtime isolation and idempotency.
# Uses POSIX sh to match the portable repository recovery gates.

#=======================# VARIABLES #=======================#
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-recurring-backup.XXXXXX")
environment_file="$work_directory/recovery.env"
backup_directory="$work_directory/backup"
source_project="tekdocs_recurring_backup_$$"
restore_project="tekdocs_recurring_restore_$$"
fixture_password=$(openssl rand -base64 36 | tr -d '\n')

#======================# FUNCTIONS #=======================#

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
#=========================# MAIN #==========================#

mkdir -p "$backup_directory"
# The container runtime owns only this per-run manifest directory.
chmod 0777 "$backup_directory"
trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$environment_file"

echo "Creating an isolated recurring-invoice recovery fixture"
compose_for "$source_project" up -d --build --wait backend
compose_for "$source_project" run --rm --no-deps -v "$backup_directory:/recovery" \
  -e TEKDOCS_FIXTURE_MODE=create \
  -e TEKDOCS_FIXTURE_PASSWORD="$fixture_password" \
  backend python manage.py shell < "$repository_root/tests/rehearsals/fixtures/recurring-invoice-recovery-fixture.py"

echo "Capturing PostgreSQL and managed media as separate backup artifacts"
compose_for "$source_project" exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_directory/postgres.dump"
docker run --rm -v "${source_project}_media_data:/source:ro" -v "$backup_directory:/backup" postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193 tar -czf /backup/media.tar.gz -C /source .
test -s "$backup_directory/postgres.dump"
test -s "$backup_directory/media.tar.gz"
compose_for "$source_project" down --volumes --remove-orphans

echo "Restoring recurring invoices into clean database and media volumes"
compose_for "$restore_project" up -d --wait db
compose_for "$restore_project" run --rm migrate
compose_for "$restore_project" exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$backup_directory/postgres.dump"
compose_for "$restore_project" build --with-dependencies backend
compose_for "$restore_project" create backend >/dev/null
docker run --rm -v "${restore_project}_media_data:/restore" -v "$backup_directory:/backup:ro" postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193 tar -xzf /backup/media.tar.gz -C /restore
compose_for "$restore_project" up -d --build --wait backend
compose_for "$restore_project" run --rm --no-deps -v "$backup_directory:/recovery" \
  -e TEKDOCS_FIXTURE_MODE=verify \
  backend python manage.py shell < "$repository_root/tests/rehearsals/fixtures/recurring-invoice-recovery-fixture.py"
compose_for "$restore_project" exec -T backend python manage.py check

echo "Recurring invoice backup/restore rehearsal passed"
