#!/bin/sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$root_dir"

report_failure() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ "$status" -ne 0 ]; then
    echo "Diagram renderer rehearsal failed; recent renderer logs follow." >&2
    docker compose logs --no-color --tail=120 diagram-renderer >&2 || true
  fi
  exit "$status"
}
trap report_failure EXIT HUP INT TERM

docker compose up -d --build --wait --wait-timeout 120 diagram-renderer
container_id=$(docker compose ps -q diagram-renderer)
test -n "$container_id"
test "$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$container_id")" = "none"
test "$(docker inspect --format '{{.Config.User}}' "$container_id")" = "10001:10001"
test "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$container_id")" = "true"
test "$(docker inspect --format '{{.HostConfig.Init}}' "$container_id")" = "true"

docker compose run --rm --no-deps \
  -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false \
  -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test \
  -e TEKDOCS_RUN_DIAGRAM_RUNTIME=true \
  backend pytest apps/core/tests/test_diagram_exports.py -q -m renderer_runtime

remaining=$(docker compose run --rm --no-deps --entrypoint sh backend -c \
  'find /app/diagram-jobs -mindepth 1 -maxdepth 1 -type d | wc -l' | tail -n 1)
test "$remaining" -eq 0
echo "Isolated diagram renderer runtime passed deterministic-byte, sandbox, and cleanup checks."
