#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-production-image.XXXXXX")
environment_file="$work_directory/production-image.env"
project_name="tekdocs_production_image_$$"

production_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" \
    -f "$repository_root/compose.production-test.yml" "$@"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "Production-target rehearsal failed; recent service logs follow." >&2
    production_compose logs --no-color --tail=120 backend frontend >&2 || true
  fi
  production_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$environment_file"

echo "Starting isolated production-target image rehearsal"
production_compose up -d --build --wait
production_compose exec -T frontend wget -q -O - http://127.0.0.1:8080/api/v1/health/ready | grep -q '"status":"ok"'
production_compose exec -T backend python manage.py migrate --check
production_compose exec -T backend python -c 'import importlib.util; assert importlib.util.find_spec("pytest") is None'
backend_id=$(production_compose ps -q backend)
backend_user=$(docker inspect --format '{{.Config.User}}' "$backend_id")
if [ "$backend_user" != "tekdocs" ] && [ "$backend_user" != "10001" ]; then
  echo "Production backend image must run as the unprivileged TekDocs user" >&2
  exit 1
fi
echo "Production-target image rehearsal passed"
