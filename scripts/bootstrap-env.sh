#!/bin/sh
set -eu

target="${1:-.env}"
if [ -e "$target" ]; then
  echo "$target already exists; leaving it unchanged"
  exit 0
fi

umask 077
postgres_password="$(openssl rand -hex 32)"
django_secret="$(openssl rand -base64 48 | tr -d '\n')"
master_key="$(openssl rand -base64 32 | tr -d '\n')"
signing_key="$(openssl rand -base64 32 | tr -d '\n')"

{
  echo "COMPOSE_PROJECT_NAME=tekdocs"
  echo "POSTGRES_DB=tekdocs"
  echo "POSTGRES_USER=tekdocs"
  echo "POSTGRES_PASSWORD=$postgres_password"
  echo "DJANGO_SECRET_KEY=$django_secret"
  echo "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend,frontend"
  echo "DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:3200"
  echo "TEKDOCS_MASTER_KEY=$master_key"
  echo "TEKDOCS_PUBLICATION_SIGNING_KEY=$signing_key"
  echo "SECURE_SSL_REDIRECT=false"
  echo "TZ=America/Chicago"
} > "$target"

echo "Created $target with generated local-only secrets"
