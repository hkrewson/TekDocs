#!/bin/sh

#=======================# Document migration upgrade #=======================#
# Preserve the database and signed PDF media across migration containers, then
# compare the same bounded migration behavior on fresh and upgraded records.

#=======================# VARIABLES #=======================#
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
fixture_override="$repository_root/tests/rehearsals/compose.document-migration.yml"

#======================# FUNCTIONS #=======================#
compose_for() {
  project=$1
  environment=$2
  directory=$3
  shift 3
  docker compose --project-name "$project" --env-file "$environment" \
    -f "$directory/compose.yml" -f "$directory/compose.test.yml" \
    -f "$fixture_override" "$@"
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
run_addressed_fixture() {
  addressed_project=$1
  addressed_environment=$2
  addressed_directory=$3
  addressed_mode=$4
  addressed_legacy_sha=${5:-}
  compose_for "$addressed_project" "$addressed_environment" "$addressed_directory" run --rm -T \
    -e TEKDOCS_KEY_ENTITY_FIXTURE_MODE="$addressed_mode" \
    -e TEKDOCS_ADDRESSED_LEGACY_SHA256="$addressed_legacy_sha" \
    migrate python manage.py shell --no-imports \
    < "$repository_root/backend/apps/core/tests/key_entity_fixture.py"
}

run_content_key_fixture() {
  content_project=$1
  content_environment=$2
  content_directory=$3
  content_mode=$4
  content_legacy_sha=${5:-}
  compose_for "$content_project" "$content_environment" "$content_directory" run --rm -T \
    -e TEKDOCS_CONTENT_KEY_FIXTURE_MODE="$content_mode" \
    -e TEKDOCS_CONTENT_KEY_LEGACY_SHA256="$content_legacy_sha" \
    migrate python manage.py shell --no-imports \
    < "$repository_root/backend/apps/core/tests/content_key_fixture.py"
}

run_diagram_fixture() {
  diagram_project=$1
  diagram_environment=$2
  diagram_directory=$3
  diagram_mode=$4
  diagram_legacy_sha=${5:-}
  compose_for "$diagram_project" "$diagram_environment" "$diagram_directory" run --rm -T \
    -e TEKDOCS_DIAGRAM_FIXTURE_MODE="$diagram_mode" \
    -e TEKDOCS_DIAGRAM_LEGACY_SHA256="$diagram_legacy_sha" \
    migrate python manage.py shell --no-imports \
    < "$repository_root/backend/apps/core/tests/diagram_fixture.py"
}

run_monitored_source_fixture() {
  monitored_source_project=$1
  monitored_source_environment=$2
  monitored_source_directory=$3
  monitored_source_mode=$4
  monitored_source_legacy_sha=${5:-}
  compose_for "$monitored_source_project" "$monitored_source_environment" "$monitored_source_directory" run --rm -T \
    -e TEKDOCS_MONITORED_SOURCE_FIXTURE_MODE="$monitored_source_mode" \
    -e TEKDOCS_MONITORED_SOURCE_LEGACY_SHA256="$monitored_source_legacy_sha" \
    migrate python manage.py shell --no-imports \
    < "$repository_root/backend/apps/core/tests/monitored_source_fixture.py"
}

run_client_publication_fixture() {
  client_publication_project=$1
  client_publication_environment=$2
  client_publication_directory=$3
  client_publication_mode=$4
  client_publication_legacy_sha=${5:-}
  compose_for "$client_publication_project" "$client_publication_environment" "$client_publication_directory" run --rm -T \
    -e TEKDOCS_CLIENT_PUBLICATION_FIXTURE_MODE="$client_publication_mode" \
    -e TEKDOCS_CLIENT_PUBLICATION_LEGACY_SHA256="$client_publication_legacy_sha" \
    migrate python manage.py shell --no-imports \
    < "$repository_root/backend/apps/core/tests/client_publication_fixture.py"
}

run_repeated_block_fixture() {
  repeated_block_project=$1
  repeated_block_environment=$2
  repeated_block_directory=$3
  repeated_block_mode=$4
  repeated_block_legacy_sha=${5:-}
  compose_for "$repeated_block_project" "$repeated_block_environment" "$repeated_block_directory" run --rm -T \
    -e TEKDOCS_REPEATED_BLOCK_FIXTURE_MODE="$repeated_block_mode" \
    -e TEKDOCS_REPEATED_BLOCK_LEGACY_SHA256="$repeated_block_legacy_sha" \
    migrate python manage.py shell --no-imports \
    < "$repository_root/backend/apps/core/tests/repeated_block_fixture.py"
}
run_cross_workspace_fixture() {
  cross_workspace_project=$1
  cross_workspace_environment=$2
  cross_workspace_directory=$3
  cross_workspace_mode=$4
  cross_workspace_legacy_sha=${5:-}
  compose_for "$cross_workspace_project" "$cross_workspace_environment" "$cross_workspace_directory" run --rm -T \
    -e TEKDOCS_CROSS_WORKSPACE_FIXTURE_MODE="$cross_workspace_mode" \
    -e TEKDOCS_CROSS_WORKSPACE_LEGACY_SHA256="$cross_workspace_legacy_sha" \
    migrate python manage.py shell --no-imports \
    < "$repository_root/backend/apps/core/tests/cross_workspace_fixture.py"
}

#=========================# MAIN #==========================#
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
# The legacy fixture uses only Django management commands. Build and run the
# original migration service (including its healthy database/SMTP dependencies)
# without rebuilding the historical HTTP/renderer stack from mutable packages.
# Current backend startup and renderer readiness remain checked below.
compose_for "$upgrade_project" "$upgrade_environment" "$baseline_directory" build migrate
compose_for "$upgrade_project" "$upgrade_environment" "$baseline_directory" run --rm -T migrate
run_fixture "$upgrade_project" "$upgrade_environment" "$baseline_directory" create > "$work_directory/baseline-ids.json"
run_addressed_fixture "$upgrade_project" "$upgrade_environment" "$baseline_directory" seed > "$work_directory/addressed-legacy.log"
addressed_upgrade_sha=$(sed -n 's/^ADDRESSED_LEGACY_SHA256=//p' "$work_directory/addressed-legacy.log")
printf '%s\n' "$addressed_upgrade_sha" | grep -Eq '^[0-9a-f]{64}$'
run_content_key_fixture "$upgrade_project" "$upgrade_environment" "$baseline_directory" seed > "$work_directory/content-legacy.log"
content_upgrade_sha=$(sed -n 's/^CONTENT_KEY_LEGACY_SHA256=//p' "$work_directory/content-legacy.log")
printf '%s\n' "$content_upgrade_sha" | grep -Eq '^[0-9a-f]{64}$'
# Render legacy STATIC graphics with the maintained isolated renderer, using the
# same project's job volume. The legacy publisher still creates/signs all rows.
compose_for "$upgrade_project" "$upgrade_environment" "$repository_root" up -d --build --wait diagram-renderer
run_diagram_fixture "$upgrade_project" "$upgrade_environment" "$baseline_directory" seed > "$work_directory/diagram-legacy.log"
run_monitored_source_fixture "$upgrade_project" "$upgrade_environment" "$baseline_directory" seed > "$work_directory/monitored_source-legacy.log"
run_client_publication_fixture "$upgrade_project" "$upgrade_environment" "$baseline_directory" seed > "$work_directory/client-publication-upgrade.log"
run_repeated_block_fixture "$upgrade_project" "$upgrade_environment" "$baseline_directory" seed > "$work_directory/repeated-block-upgrade.log"
run_cross_workspace_fixture "$upgrade_project" "$upgrade_environment" "$baseline_directory" seed > "$work_directory/cross-workspace-upgrade.log"
client_publication_upgrade_sha=$(sed -n 's/^CLIENT_PUBLICATION_LEGACY_SHA256=//p' "$work_directory/client-publication-upgrade.log")
repeated_block_upgrade_sha=$(sed -n 's/^REPEATED_BLOCK_LEGACY_SHA256=//p' "$work_directory/repeated-block-upgrade.log")
cross_workspace_upgrade_sha=$(sed -n 's/^CROSS_WORKSPACE_LEGACY_SHA256=//p' "$work_directory/cross-workspace-upgrade.log")
printf '%s\n' "$client_publication_upgrade_sha" | grep -Eq '^[0-9a-f]{64}$'
printf '%s\n' "$repeated_block_upgrade_sha" | grep -Eq '^[0-9a-f]{64}$'
printf '%s\n' "$cross_workspace_upgrade_sha" | grep -Eq '^[0-9a-f]{64}$'
diagram_upgrade_sha=$(sed -n 's/^DIAGRAM_LEGACY_SHA256=//p' "$work_directory/diagram-legacy.log")
monitored_source_upgrade_sha=$(sed -n 's/^MONITORED_SOURCE_LEGACY_SHA256=//p' "$work_directory/monitored_source-legacy.log")
printf '%s\n' "$diagram_upgrade_sha" | grep -Eq '^[0-9a-f]{64}$'
printf '%s\n' "$monitored_source_upgrade_sha" | grep -Eq '^[0-9a-f]{64}$'
compose_for "$upgrade_project" "$upgrade_environment" "$baseline_directory" down --remove-orphans

echo "Upgrading the preserved database and proving stable legacy identities"
"$repository_root/scripts/bootstrap-env.sh" "$upgrade_environment" >/dev/null
compose_for "$upgrade_project" "$upgrade_environment" "$repository_root" up -d --build --wait backend
run_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" identity > "$work_directory/upgraded-ids.json"
cmp "$work_directory/baseline-ids.json" "$work_directory/upgraded-ids.json"
compose_for "$upgrade_project" "$upgrade_environment" "$repository_root" run --rm -T migrate \
  python manage.py initialize_workspace_repositories >/dev/null
run_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" exercise > "$work_directory/upgraded-result.json"
run_addressed_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" promote "$addressed_upgrade_sha"
run_content_key_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" promote "$content_upgrade_sha"
run_diagram_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" promote "$diagram_upgrade_sha"
run_monitored_source_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" promote "$monitored_source_upgrade_sha"
run_client_publication_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" promote "$client_publication_upgrade_sha"
run_repeated_block_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" promote "$repeated_block_upgrade_sha"
run_cross_workspace_fixture "$upgrade_project" "$upgrade_environment" "$repository_root" promote "$cross_workspace_upgrade_sha"

echo "Running the identical migration workflow on a fresh installation"
compose_for "$fresh_project" "$fresh_environment" "$repository_root" up -d --build --wait backend
run_fixture "$fresh_project" "$fresh_environment" "$repository_root" create > "$work_directory/fresh-ids.json"
run_addressed_fixture "$fresh_project" "$fresh_environment" "$repository_root" seed > "$work_directory/addressed-fresh.log"
addressed_fresh_sha=$(sed -n 's/^ADDRESSED_LEGACY_SHA256=//p' "$work_directory/addressed-fresh.log")
printf '%s\n' "$addressed_fresh_sha" | grep -Eq '^[0-9a-f]{64}$'
run_content_key_fixture "$fresh_project" "$fresh_environment" "$repository_root" seed > "$work_directory/content-fresh.log"
run_diagram_fixture "$fresh_project" "$fresh_environment" "$repository_root" seed > "$work_directory/diagram-fresh.log"
run_monitored_source_fixture "$fresh_project" "$fresh_environment" "$repository_root" seed > "$work_directory/monitored_source-fresh.log"
run_client_publication_fixture "$fresh_project" "$fresh_environment" "$repository_root" seed > "$work_directory/client-publication-fresh.log"
run_repeated_block_fixture "$fresh_project" "$fresh_environment" "$repository_root" seed > "$work_directory/repeated-block-fresh.log"
run_cross_workspace_fixture "$fresh_project" "$fresh_environment" "$repository_root" seed > "$work_directory/cross-workspace-fresh.log"
client_publication_fresh_sha=$(sed -n 's/^CLIENT_PUBLICATION_LEGACY_SHA256=//p' "$work_directory/client-publication-fresh.log")
repeated_block_fresh_sha=$(sed -n 's/^REPEATED_BLOCK_LEGACY_SHA256=//p' "$work_directory/repeated-block-fresh.log")
cross_workspace_fresh_sha=$(sed -n 's/^CROSS_WORKSPACE_LEGACY_SHA256=//p' "$work_directory/cross-workspace-fresh.log")
printf '%s\n' "$client_publication_fresh_sha" | grep -Eq '^[0-9a-f]{64}$'
printf '%s\n' "$repeated_block_fresh_sha" | grep -Eq '^[0-9a-f]{64}$'
printf '%s\n' "$cross_workspace_fresh_sha" | grep -Eq '^[0-9a-f]{64}$'
diagram_fresh_sha=$(sed -n 's/^DIAGRAM_LEGACY_SHA256=//p' "$work_directory/diagram-fresh.log")
monitored_source_fresh_sha=$(sed -n 's/^MONITORED_SOURCE_LEGACY_SHA256=//p' "$work_directory/monitored_source-fresh.log")
printf '%s\n' "$diagram_fresh_sha" | grep -Eq '^[0-9a-f]{64}$'
printf '%s\n' "$monitored_source_fresh_sha" | grep -Eq '^[0-9a-f]{64}$'

content_fresh_sha=$(sed -n 's/^CONTENT_KEY_LEGACY_SHA256=//p' "$work_directory/content-fresh.log")
printf '%s\n' "$content_fresh_sha" | grep -Eq '^[0-9a-f]{64}$'
run_fixture "$fresh_project" "$fresh_environment" "$repository_root" identity > "$work_directory/fresh-verified-ids.json"
cmp "$work_directory/fresh-ids.json" "$work_directory/fresh-verified-ids.json"
compose_for "$fresh_project" "$fresh_environment" "$repository_root" run --rm -T migrate \
  python manage.py initialize_workspace_repositories >/dev/null
run_fixture "$fresh_project" "$fresh_environment" "$repository_root" exercise > "$work_directory/fresh-result.json"
run_addressed_fixture "$fresh_project" "$fresh_environment" "$repository_root" promote "$addressed_fresh_sha"
run_content_key_fixture "$fresh_project" "$fresh_environment" "$repository_root" promote "$content_fresh_sha"
run_diagram_fixture "$fresh_project" "$fresh_environment" "$repository_root" promote "$diagram_fresh_sha"
run_monitored_source_fixture "$fresh_project" "$fresh_environment" "$repository_root" promote "$monitored_source_fresh_sha"
run_client_publication_fixture "$fresh_project" "$fresh_environment" "$repository_root" promote "$client_publication_fresh_sha"
run_repeated_block_fixture "$fresh_project" "$fresh_environment" "$repository_root" promote "$repeated_block_fresh_sha"
run_cross_workspace_fixture "$fresh_project" "$fresh_environment" "$repository_root" promote "$cross_workspace_fresh_sha"
cmp "$work_directory/upgraded-result.json" "$work_directory/fresh-result.json"

echo "Document migration fresh/0.8.46 upgrade acceptance passed"
