#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
baseline_ref=${TEKDOCS_NETWORK_UPGRADE_FROM_REF:-2f15710}
expected_baseline_version=${TEKDOCS_NETWORK_UPGRADE_FROM_VERSION:-0.4.9}
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-network-upgrade.XXXXXX")
baseline_directory="$work_directory/baseline"
environment_file="$work_directory/upgrade.env"
project_name="tekdocs_network_upgrade_$$"
fixture_password=$(openssl rand -base64 36 | tr -d '\n')

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
  if [ "$exit_status" -ne 0 ]; then
    current_compose logs --no-color migrate backend >&2 || true
  fi
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

baseline_version=$(tr -d '[:space:]' < "$baseline_directory/VERSION")
current_version=$(tr -d '[:space:]' < "$repository_root/VERSION")
if [ "$baseline_version" != "$expected_baseline_version" ]; then
  echo "Network upgrade expected baseline $expected_baseline_version, found $baseline_version" >&2
  exit 1
fi
if [ "$current_version" = "$baseline_version" ]; then
  echo "Network upgrade requires a version newer than $baseline_version" >&2
  exit 1
fi

echo "Creating retained network data in TekDocs $baseline_version"
baseline_compose up -d --build --wait backend
baseline_compose exec -T \
  -e TEKDOCS_FIXTURE_MODE=create \
  -e TEKDOCS_FIXTURE_PASSWORD="$fixture_password" \
  backend python manage.py shell < "$repository_root/scripts/network-certification-fixture.py"
baseline_compose down --remove-orphans

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
echo "Applying TekDocs $current_version to the retained $baseline_version network data"
current_compose up -d --build --wait backend
current_compose exec -T \
  -e TEKDOCS_FIXTURE_MODE=verify \
  backend python manage.py shell < "$repository_root/scripts/network-certification-fixture.py"
current_compose exec -T backend python manage.py check
current_compose exec -T backend python manage.py makemigrations --check --dry-run

echo "Network upgrade rehearsal passed: $baseline_version -> $current_version"
