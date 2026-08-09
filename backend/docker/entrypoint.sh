#!/bin/sh
set -eu

if [ "${TEKDOCS_VALIDATE_RUNTIME_DATABASE:-false}" = "true" ]; then
  python manage.py validate_runtime_database
fi

exec "$@"
