#!/bin/sh
set -eu

target="${1:-.env}"
if [ -e "$target" ]; then
  if grep -q '^TEKDOCS_BOOTSTRAP_TOKEN=' "$target"; then
    echo "$target already contains the required generated secrets; leaving it unchanged"
    exit 0
  fi
  umask 077
  bootstrap_token="$(openssl rand -base64 32 | tr -d '\n')"
  echo "TEKDOCS_BOOTSTRAP_TOKEN=$bootstrap_token" >> "$target"
  echo "Added the missing generated bootstrap token to $target without changing existing values"
  exit 0
fi

umask 077
postgres_password="$(openssl rand -hex 32)"
django_secret="$(openssl rand -base64 48 | tr -d '\n')"
master_key="$(openssl rand -base64 32 | tr -d '\n')"
signing_key="$(openssl rand -base64 32 | tr -d '\n')"
bootstrap_token="$(openssl rand -base64 32 | tr -d '\n')"

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
  echo "TEKDOCS_BOOTSTRAP_TOKEN=$bootstrap_token"
  echo "TEKDOCS_PUBLIC_URL=http://localhost:3200"
  echo "TEKDOCS_ALLOW_INSECURE_PUBLIC_URL=true"
  echo "INVITATION_TTL_HOURS=168"
  echo "PASSWORD_RESET_TIMEOUT_SECONDS=3600"
  echo "MAILPIT_UI_PORT=8025"
  echo "EMAIL_HOST=mailpit"
  echo "EMAIL_PORT=1025"
  echo "EMAIL_HOST_USER="
  echo "EMAIL_HOST_PASSWORD="
  echo "EMAIL_USE_TLS=false"
  echo "EMAIL_USE_SSL=false"
  echo "EMAIL_TIMEOUT=10"
  echo "DEFAULT_FROM_EMAIL=TekDocs <noreply@tekdocs.local>"
  echo "TEKDOCS_ALLOW_INSECURE_SMTP=true"
  echo "SECURE_SSL_REDIRECT=false"
  echo "TZ=America/Chicago"
} > "$target"

echo "Created $target with generated local-only secrets"
