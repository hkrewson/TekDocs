#!/bin/sh
set -eu

if [ "${TEKDOCS_RUN_MIGRATIONS:-false}" = "true" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
fi

exec "$@"
