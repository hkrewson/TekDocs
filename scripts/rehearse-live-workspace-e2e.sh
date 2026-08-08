#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-live-workspace.XXXXXX")
environment_file="$work_directory/live-workspace.env"
project_name="tekdocs_live_workspace_$$"
playwright_image="tekdocs-live-workspace-e2e:local"

live_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "Live workspace journey failed; recent service logs follow." >&2
    live_compose logs --no-color --tail=120 backend frontend >&2 || true
  fi
  live_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  docker image rm -f "$playwright_image" >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
  echo "DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8080"
  echo "TEKDOCS_PUBLIC_URL=http://localhost:8080"
} >> "$environment_file"
bootstrap_token=$(sed -n 's/^TEKDOCS_BOOTSTRAP_TOKEN=//p' "$environment_file")
playwright_version=1.62.1
if ! grep -A 3 '"node_modules/@playwright/test"' "$repository_root/frontend/package-lock.json" | grep -q '"version": "1.62.1"'; then
  echo "Update the live Playwright image version to match package-lock.json." >&2
  exit 1
fi

echo "Starting isolated real-stack workspace browser journey"
live_compose up -d --build --wait
docker build --build-arg "PLAYWRIGHT_VERSION=$playwright_version" -f "$repository_root/frontend/Dockerfile.e2e" -t "$playwright_image" "$repository_root/frontend" >/dev/null
frontend_id=$(live_compose ps -q frontend)
docker run --rm \
  --network "container:$frontend_id" \
  -e PLAYWRIGHT_BASE_URL=http://localhost:8080 \
  -e TEKDOCS_E2E_BOOTSTRAP_TOKEN="$bootstrap_token" \
  "$playwright_image" npx playwright test --config=playwright.live.config.ts

live_compose exec -T backend python manage.py shell -c '
from apps.core.models import Organization
organization = Organization.objects.select_related("entity").get(entity__display_name="Live Acme Client")
assert organization.entity.organization_id is None
assert organization.tenant.name == "Live Workspace MSP"
assert organization.classifications.filter(kind="client").exists()
assert organization.classifications.filter(kind="vendor").exists()
print("Live workspace database fixture verified")
'
echo "Real browser-to-Django-to-PostgreSQL workspace journey passed"
