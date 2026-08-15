#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-notification-outage.XXXXXX")
environment_file="$work_directory/outage.env"
project_name="tekdocs_notification_outage_$$"
fixture_password=$(openssl rand -base64 36 | tr -d '\n')

compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  exit_status=$?
  if [ "$exit_status" -ne 0 ]; then
    compose logs --no-color backend mailpit >&2 || true
  fi
  compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
  exit "$exit_status"
}
trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$environment_file"

compose up -d --build --wait backend
compose exec -T -e TEKDOCS_FIXTURE_MODE=create -e TEKDOCS_FIXTURE_PASSWORD="$fixture_password" \
  backend python manage.py shell < "$repository_root/tests/rehearsals/fixtures/notification-mail-outage-fixture.py"
compose stop mailpit
compose exec -T -e TEKDOCS_FIXTURE_MODE=outage backend python manage.py shell \
  < "$repository_root/tests/rehearsals/fixtures/notification-mail-outage-fixture.py"
compose up -d --wait mailpit
compose exec -T -e TEKDOCS_FIXTURE_MODE=recover backend python manage.py shell \
  < "$repository_root/tests/rehearsals/fixtures/notification-mail-outage-fixture.py"

echo "Notification mail-outage rehearsal passed: queued safely while SMTP was down and delivered after recovery"
