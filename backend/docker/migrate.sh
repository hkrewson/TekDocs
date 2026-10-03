#!/bin/sh
set -eu

python manage.py provision_runtime_role
python manage.py migrate --noinput
python manage.py initialize_workspace_repositories
python manage.py collectstatic --noinput
