#!/bin/sh
set -eu

# Compare the same first-wave migration behavior on fresh and 0.8.46-upgraded data.
repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
baseline_ref=35e93cabdfa3e1ae2b32f447ca7a09f21f6d16a8
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-document-migration.XXXXXX")
baseline_directory="$work_directory/baseline"
upgrade_environment="$work_directory/upgrade.env"
fresh_environment="$work_directory/fresh.env"
upgrade_project="tekdocs_document_migration_upgrade_$$"
fresh_project="tekdocs_document_migration_fresh_$$"
fixture_password=$(openssl rand -base64 36 | tr -d '\n')

compose_for() {
  project=$1
  environment=$2
  directory=$3
  shift 3
  docker compose --project-name "$project" --env-file "$environment" \
    -f "$directory/compose.yml" -f "$directory/compose.test.yml" "$@"
}

run_fixture() {
  project=$1
  environment=$2
  directory=$3
  mode=$4
  compose_for "$project" "$environment" "$directory" run --rm -T \
    -e TEKDOCS_FIXTURE_MODE="$mode" \
    -e TEKDOCS_FIXTURE_EMAIL="migration-rehearsal-$$@example.invalid" \
    -e TEKDOCS_FIXTURE_PASSWORD="$fixture_password" \
    migrate python manage.py shell --no-imports \
    < "$repository_root/tests/rehearsals/fixtures/document-migration-fixture.py"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "Document migration upgrade rehearsal failed; backend diagnostics follow." >&2
    compose_for "$upgrade_project" "$upgrade_environment" "$repository_root" logs --no-color --tail 100 migrate backend >&2 || true
    compose_for "$fresh_project" "$fresh_environment" "$repository_root" logs --no-color --tail 100 migrate backend >&2 || true
  fi
  compose_for "$upgrade_project" "$upgrade_environment" "$repository_root" down --volumes --remove-orphans >/dev/null 2>&1 || true
  compose_for "$fresh_project" "$fresh_environment" "$repository_root" down --volumes --remove-orphans >/dev/null 2>&1 || true
  [ -n "$work_directory" ] && [ -d "$work_directory" ] && rm -rf "$work_directory"
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

[ "$(git -C "$repository_root" show "$baseline_ref:VERSION" | tr -d '[:space:]')" = "0.8.46" ]
mkdir -p "$baseline_directory"
git -C "$repository_root" archive "$baseline_ref" | tar -x -C "$baseline_directory"
"$baseline_directory/scripts/bootstrap-env.sh" "$upgrade_environment" >/dev/null
"$repository_root/scripts/bootstrap-env.sh" "$fresh_environment" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$upgrade_environment"
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$fresh_environment"

echo "Creating legacy documents on isolated TekDocs 0.8.46"
compose_for "$upgrade_project" "$upgrade_environment" "$baseline_directory" up -d --build --wait backend
run_fixture "$upgrade_project" "$upgrade_environment" "$baseline_directory" create > "$work_directory/baseline-ids.json"
compose_for "$upgrade_project" "$upgrade_environment" "$baseline_directory" down --remove-orphans

echo "Upgrading the preserved database and proving stable legacy identities"
"$repository_root/scripts/bootstrap-env.sh" "$upgrade_environment" >/dev/null
compose_for "$upgrade_project" "$upgrade_environment" "$repository_root" up -d --build --wait backend
run_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" identity > "$work_directory/upgraded-ids.json"
cmp "$work_directory/baseline-ids.json" "$work_directory/upgraded-ids.json"
compose_for "$upgrade_project" "$upgrade_environment" "$repository_root" run --rm -T migrate \
  python manage.py initialize_workspace_repositories >/dev/null
run_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" exercise > "$work_directory/upgraded-result.json"

echo "Running the identical migration workflow on a fresh installation"
compose_for "$fresh_project" "$fresh_environment" "$repository_root" up -d --build --wait backend
run_fixture "$fresh_project" "$fresh_environment" "$repository_root" create > "$work_directory/fresh-ids.json"
run_fixture "$fresh_project" "$fresh_environment" "$repository_root" identity > "$work_directory/fresh-verified-ids.json"
cmp "$work_directory/fresh-ids.json" "$work_directory/fresh-verified-ids.json"
compose_for "$fresh_project" "$fresh_environment" "$repository_root" run --rm -T migrate \
  python manage.py initialize_workspace_repositories >/dev/null
run_fixture "$fresh_project" "$fresh_environment" "$repository_root" exercise > "$work_directory/fresh-result.json"
cmp "$work_directory/upgraded-result.json" "$work_directory/fresh-result.json"

echo "Document migration fresh/0.8.46 upgrade acceptance passed"
