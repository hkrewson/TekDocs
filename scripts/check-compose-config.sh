#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd -P)

bash -n \
  "$repository_root/scripts/setup-production.sh" \
  "$repository_root/scripts/update-production.sh" \
  "$repository_root/scripts/lib/production-images.sh"
"$repository_root/scripts/bootstrap-env.sh" --help >/dev/null
"$repository_root/scripts/setup-production.sh" --help >/dev/null
"$repository_root/tests/rehearsals/test-production-setup.sh"

TEKDOCS_BACKEND_IMAGE=ghcr.io/hkrewson/tekdocs-backend@sha256:0000000000000000000000000000000000000000000000000000000000000000 \
TEKDOCS_FRONTEND_IMAGE=ghcr.io/hkrewson/tekdocs-frontend@sha256:0000000000000000000000000000000000000000000000000000000000000000 \
docker compose \
  --env-file "$repository_root/.env.production.example" \
  -f "$repository_root/compose.yml" \
  -f "$repository_root/compose.production.yml" \
  -f "$repository_root/compose.secret-files.yml" \
  -f "$repository_root/compose.images.yml" \
  -f "$repository_root/compose.traefik.yml" \
  config --quiet

rendered=$(TEKDOCS_BACKEND_IMAGE=ghcr.io/hkrewson/tekdocs-backend@sha256:0000000000000000000000000000000000000000000000000000000000000000 \
  TEKDOCS_FRONTEND_IMAGE=ghcr.io/hkrewson/tekdocs-frontend@sha256:0000000000000000000000000000000000000000000000000000000000000000 \
  docker compose \
  --env-file "$repository_root/.env.production.example" \
  -f "$repository_root/compose.yml" \
  -f "$repository_root/compose.production.yml" \
  -f "$repository_root/compose.secret-files.yml" \
  -f "$repository_root/compose.images.yml" \
  -f "$repository_root/compose.traefik.yml" \
  config)

printf '%s\n' "$rendered" | grep -q 'image: ghcr.io/hkrewson/tekdocs-backend@sha256:'
printf '%s\n' "$rendered" | grep -q 'image: ghcr.io/hkrewson/tekdocs-frontend@sha256:'
if printf '%s\n' "$rendered" | grep -q 'build:'; then
  echo "The production image overlay must remove application build definitions." >&2
  exit 1
fi

echo "Production Traefik Compose contract passed."
