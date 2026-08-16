#!/bin/sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$root_dir"

docker compose up -d --build diagram-renderer
container_id=$(docker compose ps -q diagram-renderer)
test -n "$container_id"
test "$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$container_id")" = "none"
test "$(docker inspect --format '{{.Config.User}}' "$container_id")" = "10001:10001"
test "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$container_id")" = "true"

docker compose run --rm --no-deps \
  -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false \
  -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test \
  -e TEKDOCS_RUN_DIAGRAM_RUNTIME=true \
  backend pytest apps/core/tests/test_diagram_exports.py -q -m renderer_runtime

remaining=$(docker compose run --rm --no-deps backend sh -c \
  'find /app/diagram-jobs -mindepth 1 -maxdepth 1 -type d | wc -l' | tail -n 1)
test "$remaining" -eq 0
echo "Isolated diagram renderer runtime passed deterministic-byte, sandbox, and cleanup checks."
