#!/bin/sh
set -eu

#=================# Repository Foundation Acceptance #=================#
#
# Compose the complete 0.9.1 repository boundary in production-shaped
# containers. The rehearsal proves isolated workspace custody, deterministic
# manifests, interrupted-write recovery, container persistence, and exact
# network-isolated restore without GitHub authority.

#=======================# VARIABLES #=======================#

repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-repository-foundation.XXXXXX")
source_environment="$work_directory/source.env"
restore_environment="$work_directory/restore.env"
source_secrets="$work_directory/source-secrets"
restored_secrets="$work_directory/restored-secrets"
backup_directory="$work_directory/encrypted-backup"
recovery_key="$work_directory/recovery.key"
source_inventory="$work_directory/source-inventory.json"
restored_inventory="$work_directory/restored-inventory.json"
source_project="tekdocs_repository_foundation_source_$$"
restore_project="tekdocs_repository_foundation_restore_$$"
fixture_password=$(openssl rand -base64 36 | tr -d '\n')

#======================# FUNCTIONS #=======================#

compose_for() {
  environment=$1
  secret_directory=$2
  shift 2
  TEKDOCS_SECRET_DIRECTORY="$secret_directory" docker compose --env-file "$environment" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" \
    -f "$repository_root/compose.production.yml" -f "$repository_root/compose.secret-files.yml" \
    -f "$repository_root/compose.bootstrap-secret.yml" "$@"
}

copy_secret() {
  name=$1
  target=$2
  value=$(sed -n "s/^${name}=//p" "$source_environment" | head -n 1)
  [ -n "$value" ] || { echo "Repository acceptance could not prepare $name." >&2; exit 1; }
  printf '%s\n' "$value" > "$source_secrets/$target"
  chmod 0600 "$source_secrets/$target"
}

run_fixture() {
  environment=$1
  secret_directory=$2
  mode=$3
  compose_for "$environment" "$secret_directory" exec -T \
    -e TEKDOCS_FIXTURE_MODE="$mode" \
    -e TEKDOCS_FIXTURE_PASSWORD="$fixture_password" \
    backend python manage.py shell --no-imports \
    < "$repository_root/tests/rehearsals/fixtures/repository-foundation-fixture.py"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "Repository foundation acceptance failed; retained backend diagnostics follow." >&2
    compose_for "$source_environment" "$source_secrets" logs --no-color --tail 120 backend >&2 || true
    compose_for "$restore_environment" "$restored_secrets" logs --no-color --tail 120 backend >&2 || true
  fi
  compose_for "$source_environment" "$source_secrets" down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  compose_for "$restore_environment" "$restored_secrets" down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
  exit "$status"
}

#=========================# MAIN #==========================#

trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$source_environment" >/dev/null
mkdir -m 0700 "$source_secrets"
copy_secret DJANGO_SECRET_KEY django_secret_key
copy_secret POSTGRES_OWNER_PASSWORD postgres_owner_password
copy_secret POSTGRES_RUNTIME_PASSWORD postgres_runtime_password
copy_secret TEKDOCS_MASTER_KEY tekdocs_master_key
copy_secret TEKDOCS_PUBLICATION_SIGNING_KEY publication_signing_key
copy_secret TEKDOCS_BOOTSTRAP_TOKEN bootstrap_token
sed -E \
  -e 's/^COMPOSE_PROJECT_NAME=.*/COMPOSE_PROJECT_NAME='"$source_project"'/' \
  -e 's/^(DJANGO_SECRET_KEY|POSTGRES_OWNER_PASSWORD|POSTGRES_RUNTIME_PASSWORD|TEKDOCS_MASTER_KEY|TEKDOCS_PUBLICATION_SIGNING_KEY|TEKDOCS_BOOTSTRAP_TOKEN)=.*/\1=/' \
  "$source_environment" > "$source_environment.sanitized"
mv "$source_environment.sanitized" "$source_environment"
chmod 0600 "$source_environment"
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$source_environment"
sed 's/^COMPOSE_PROJECT_NAME=.*/COMPOSE_PROJECT_NAME='"$restore_project"'/' \
  "$source_environment" > "$restore_environment"
chmod 0600 "$restore_environment"
"$repository_root/scripts/generate-recovery-key.sh" "$recovery_key" >/dev/null

echo "Creating the three-workspace repository acceptance fixture"
compose_for "$source_environment" "$source_secrets" up -d --build --wait backend worker
run_fixture "$source_environment" "$source_secrets" create >/dev/null
compose_for "$source_environment" "$source_secrets" exec -T \
  backend python manage.py initialize_workspace_repositories >/dev/null

echo "Exercising isolation, deterministic manifests, and interrupted-write recovery"
run_fixture "$source_environment" "$source_secrets" exercise >/dev/null

echo "Recreating repository-owning containers against the same managed volume"
original_backend=$(compose_for "$source_environment" "$source_secrets" ps -q backend)
original_worker=$(compose_for "$source_environment" "$source_secrets" ps -q worker)
compose_for "$source_environment" "$source_secrets" up -d --force-recreate --no-deps --wait backend worker
[ "$(compose_for "$source_environment" "$source_secrets" ps -q backend)" != "$original_backend" ]
[ "$(compose_for "$source_environment" "$source_secrets" ps -q worker)" != "$original_worker" ]
run_fixture "$source_environment" "$source_secrets" verify >/dev/null
run_fixture "$source_environment" "$source_secrets" inventory > "$source_inventory"

echo "Capturing the complete encrypted recovery set"
"$repository_root/scripts/tekdocs-backup.sh" --env-file "$source_environment" \
  --secret-directory "$source_secrets" --key-file "$recovery_key" --output "$backup_directory"

echo "Restoring the exact accepted heads on a clean network-isolated stack"
"$repository_root/scripts/tekdocs-restore.sh" --env-file "$restore_environment" \
  --backup "$backup_directory" --key-file "$recovery_key" \
  --secret-output "$restored_secrets" --confirm-destroy "$restore_project" --network-isolated
[ "$(docker network inspect "${restore_project}_internal" --format '{{.Internal}}')" = true ]
compose_for "$restore_environment" "$restored_secrets" exec -T backend python -c \
  'import os; assert not any(name.startswith(("GITHUB_", "GH_")) for name in os.environ)'
run_fixture "$restore_environment" "$restored_secrets" verify >/dev/null
run_fixture "$restore_environment" "$restored_secrets" inventory > "$restored_inventory"
cmp "$source_inventory" "$restored_inventory"

echo "Repository foundation composed acceptance passed"
