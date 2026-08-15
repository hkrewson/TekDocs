#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-browser-e2e.XXXXXX")
environment_file="$work_directory/browser.env"
project_name="tekdocs_browser_e2e_$$"
playwright_image="tekdocs-browser-e2e:local"
browser_scope=${1:-all}
safe_artifact_directory="$repository_root/artifacts/playwright-safe"
safe_summary="$safe_artifact_directory/$browser_scope.json"
quarantine_directory="$repository_root/artifacts/playwright-quarantine"
quarantine_summary="$quarantine_directory/$browser_scope.json"

browser_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "Browser rehearsal failed; recent service logs follow." >&2
    browser_compose logs --no-color --tail=100 backend frontend >&2 || true
  fi
  browser_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  docker image rm -f "$playwright_image" >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

case "$browser_scope" in
  chromium|firefox|webkit|mobile-chromium|mobile-webkit) project_argument="--project=$browser_scope" ;;
  all) project_argument="" ;;
  *) echo "Usage: $0 [chromium|firefox|webkit|mobile-chromium|mobile-webkit|all]" >&2; exit 2 ;;
esac

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$environment_file"

playwright_version=1.62.1
if ! grep -A 3 '"node_modules/@playwright/test"' "$repository_root/frontend/package-lock.json" | grep -q '"version": "1.62.1"'; then
  echo "Update the browser Playwright image version to match package-lock.json." >&2
  exit 1
fi

echo "Starting isolated $browser_scope browser suite"
mkdir -p "$safe_artifact_directory"
mkdir -p "$quarantine_directory"
rm -f "$safe_summary" "$quarantine_summary"
browser_compose up -d --build --wait backend frontend
docker build --build-arg "PLAYWRIGHT_VERSION=$playwright_version" -f "$repository_root/frontend/Dockerfile.e2e" -t "$playwright_image" "$repository_root/frontend" >/dev/null
frontend_id=$(browser_compose ps -q frontend)
test_status=0
docker run --rm \
  --network "container:$frontend_id" \
  -e PLAYWRIGHT_BASE_URL=http://localhost:8080 \
  -e "PLAYWRIGHT_SAFE_SUMMARY=/app/quarantine/$browser_scope.json" \
  -e PLAYWRIGHT_OUTPUT_DIR=/tmp/tekdocs-playwright-results \
  -v "$quarantine_directory:/app/quarantine" \
  "$playwright_image" sh -c \
  "npx playwright test --config=playwright.compose.config.ts $project_argument; status=\$?; \
  if [ -f \"\$PLAYWRIGHT_SAFE_SUMMARY\" ]; then chmod 0644 \"\$PLAYWRIGHT_SAFE_SUMMARY\"; fi; \
  exit \"\$status\"" || test_status=$?
"$repository_root/scripts/check-browser-artifacts.sh" "$quarantine_summary"
mv "$quarantine_summary" "$safe_summary"
[ "$test_status" -eq 0 ] || exit "$test_status"
echo "$browser_scope browser suite passed"
