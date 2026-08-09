#!/bin/sh
set -eu

generated="$(mktemp /tmp/tekdocs-openapi.XXXXXX)"
trap 'rm -f "$generated"' EXIT

docker compose run --rm --no-deps \
  -e TEKDOCS_VALIDATE_RUNTIME_DATABASE=false \
  -e DJANGO_SETTINGS_MODULE=tekdocs.settings.test \
  backend python manage.py spectacular --validate > "$generated"

if ! diff -u backend/openapi.yml "$generated"; then
  echo "OpenAPI drift detected; run make schema" >&2
  exit 1
fi
