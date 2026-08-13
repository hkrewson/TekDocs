#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-browser-performance.XXXXXX")
environment_file="$work_directory/performance.env"
project_name="tekdocs_browser_performance_$$"
playwright_image="tekdocs-browser-performance:local"
performance_artifacts="$repository_root/artifacts/playwright-performance"

performance_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "Browser performance rehearsal failed; recent service logs follow." >&2
    performance_compose logs --no-color --tail=100 backend frontend >&2 || true
  fi
  performance_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  docker image rm -f "$playwright_image" >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

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

echo "Starting isolated constrained-device browser performance suite"
rm -rf "$performance_artifacts"
mkdir -p "$performance_artifacts"
performance_compose up -d --build --wait backend frontend
docker build --build-arg "PLAYWRIGHT_VERSION=$playwright_version" -f "$repository_root/frontend/Dockerfile.e2e" -t "$playwright_image" "$repository_root/frontend" >/dev/null
frontend_id=$(performance_compose ps -q frontend)
docker run --rm \
  --network "container:$frontend_id" \
  -v "$performance_artifacts:/app/test-results" \
  -e PLAYWRIGHT_BASE_URL=http://localhost:8080 \
  -e TEKDOCS_PERFORMANCE_REHEARSAL=true \
  "$playwright_image" npx playwright test --config=playwright.compose.config.ts --project=chromium e2e/performance.spec.ts
echo "Constrained-device browser performance suite passed"
