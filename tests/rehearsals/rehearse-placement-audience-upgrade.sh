#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
baseline_ref=${TEKDOCS_PLACEMENT_AUDIENCE_UPGRADE_FROM_REF:-57be83f}
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-placement-audience-upgrade.XXXXXX")
baseline_directory="$work_directory/baseline"
environment_file="$work_directory/upgrade.env"
project_name="tekdocs_placement_audience_upgrade_$$"
fixture_password=$(openssl rand -base64 36 | tr -d '\n')
production_override="$repository_root/tests/rehearsals/compose.production-image.yml"
fixture="$repository_root/tests/rehearsals/fixtures/placement-audience-upgrade-fixture.py"

baseline_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$baseline_directory/compose.yml" -f "$baseline_directory/compose.test.yml" \
    -f "$production_override" "$@"
}

current_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" \
    -f "$production_override" "$@"
}

cleanup() {
  exit_status=$?
  if [ "$exit_status" -ne 0 ]; then
    current_compose logs --no-color --tail=200 migrate backend >&2 || true
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
  echo "TEKDOCS_ATTACHMENT_SCANNER=apps.core.attachment_security.ClamAVAttachmentScanner"
  echo "TEKDOCS_CLAMAV_HOST=clamav.invalid"
} >> "$environment_file"

baseline_version=$(tr -d '[:space:]' < "$baseline_directory/VERSION")
current_version=$(tr -d '[:space:]' < "$repository_root/VERSION")
if [ "$baseline_version" != "0.8.39" ]; then
  echo "Placement-audience upgrade expected baseline 0.8.39, found $baseline_version" >&2
  exit 1
fi
if [ "$current_version" != "0.8.42" ]; then
  echo "Placement-audience upgrade expected current version 0.8.42, found $current_version" >&2
  exit 1
fi

echo "Creating exact 0.8.39 placement and signed publication evidence"
baseline_compose up -d --build --wait backend
baseline_compose exec -T -e TEKDOCS_FIXTURE_MODE=create -e TEKDOCS_FIXTURE_PASSWORD="$fixture_password" \
  backend python manage.py shell < "$fixture"
baseline_compose down --remove-orphans

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
echo "Applying production image $current_version to the exact $baseline_version database and media"
current_compose up -d --build --wait backend
current_compose exec -T -e TEKDOCS_FIXTURE_MODE=verify backend python manage.py shell < "$fixture"
current_compose exec -T backend python manage.py check
current_compose exec -T backend sh -c 'test "$TEKDOCS_IMAGE_VARIANT" = production'

echo "Placement-audience production-image upgrade rehearsal passed: $baseline_version -> $current_version"
