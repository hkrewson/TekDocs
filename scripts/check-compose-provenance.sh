#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd -P)
container_ids=$(docker compose -f "$repository_root/compose.yml" ps -q)
if [ -z "$container_ids" ]; then
  echo "No TekDocs Compose services are running; provenance check skipped."
  exit 0
fi

failed=false
for container_id in $container_ids; do
  working_directory=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$container_id")
  container_name=$(docker inspect --format '{{ .Name }}' "$container_id" | sed 's#^/##')
  if [ "$working_directory" != "$repository_root" ]; then
    echo "$container_name was created from $working_directory, expected $repository_root" >&2
    failed=true
  fi
done

if [ "$failed" = true ]; then
  echo "Recreate services from the canonical checkout with: docker compose up -d --build --force-recreate" >&2
  exit 1
fi
echo "Running Compose services were created from $repository_root"
