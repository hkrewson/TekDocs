#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
baseline_ref=${TEKDOCS_INTEGRATION_UPGRADE_FROM_REF:-d3b7c4d}
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-integration-upgrade.XXXXXX")
baseline_directory="$work_directory/baseline"
environment_file="$work_directory/upgrade.env"
project_name="tekdocs_integration_upgrade_$$"
fixture_password=$(openssl rand -base64 36 | tr -d '\n')
provider_token=$(openssl rand -base64 48 | tr -d '\n')

baseline_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$baseline_directory/compose.yml" -f "$baseline_directory/compose.test.yml" "$@"
}
current_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}
cleanup() {
  exit_status=$?
  if [ "$exit_status" -ne 0 ]; then current_compose logs --no-color migrate backend >&2 || true; fi
  current_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
  exit "$exit_status"
}
trap cleanup EXIT HUP INT TERM

git -C "$repository_root" cat-file -e "$baseline_ref^{commit}"
mkdir -p "$baseline_directory"
git -C "$repository_root" archive "$baseline_ref" | tar -x -C "$baseline_directory"
"$baseline_directory/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$environment_file"
[ "$(tr -d '[:space:]' < "$baseline_directory/VERSION")" = "0.6.8" ]
[ "$(tr -d '[:space:]' < "$repository_root/VERSION")" = "0.6.9" ]

baseline_compose up -d --build --wait backend
baseline_compose exec -T -e TEKDOCS_FIXTURE_MODE=create -e TEKDOCS_FIXTURE_PASSWORD="$fixture_password" \
  -e TEKDOCS_FIXTURE_PROVIDER_TOKEN="$provider_token" backend python manage.py shell \
  < "$repository_root/scripts/integration-runtime-fixture.py"
baseline_compose down --remove-orphans

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
current_compose up -d --build --wait backend worker scheduler
current_compose exec -T -e TEKDOCS_FIXTURE_MODE=verify -e TEKDOCS_FIXTURE_PROVIDER_TOKEN="$provider_token" \
  backend python manage.py shell < "$repository_root/scripts/integration-runtime-fixture.py"
current_compose exec -T backend python manage.py check
current_compose exec -T backend python manage.py makemigrations --check --dry-run
echo "Integration upgrade rehearsal passed: 0.6.8 -> 0.6.9"
