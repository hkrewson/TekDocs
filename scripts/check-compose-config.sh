#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd -P)

docker compose \
  --env-file "$repository_root/.env.example" \
  -f "$repository_root/compose.yml" \
  -f "$repository_root/compose.production.yml" \
  -f "$repository_root/compose.secret-files.yml" \
  -f "$repository_root/compose.traefik.yml" \
  config --quiet

echo "Production Traefik Compose contract passed."
