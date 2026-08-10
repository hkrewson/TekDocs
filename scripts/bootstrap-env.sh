#!/bin/sh
set -eu

target="${1:-.env}"

generate_url_safe_32_byte_key() {
  openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'
}

if [ -e "$target" ]; then
  umask 077
  changed=false
  if ! grep -q '^TEKDOCS_BOOTSTRAP_TOKEN=' "$target"; then
    echo "TEKDOCS_BOOTSTRAP_TOKEN=$(openssl rand -base64 32 | tr -d '\n')" >> "$target"
    changed=true
  fi
  if ! grep -q '^TEKDOCS_PUBLICATION_SIGNING_KEY=' "$target"; then
    echo "TEKDOCS_PUBLICATION_SIGNING_KEY=$(generate_url_safe_32_byte_key)" >> "$target"
    changed=true
  else
    existing_signing_key=$(sed -n 's/^TEKDOCS_PUBLICATION_SIGNING_KEY=//p' "$target" | head -n 1)
    if printf '%s' "$existing_signing_key" | grep -Eq '^[A-Za-z0-9+/]{43}=$' \
      && printf '%s' "$existing_signing_key" | grep -Eq '[+/]'; then
      normalized_signing_key=$(printf '%s' "$existing_signing_key" | tr '+/' '-_')
      temporary_target=$(mktemp "${target}.XXXXXX")
      sed "s|^TEKDOCS_PUBLICATION_SIGNING_KEY=.*$|TEKDOCS_PUBLICATION_SIGNING_KEY=$normalized_signing_key|" \
        "$target" > "$temporary_target"
      chmod 0600 "$temporary_target"
      mv "$temporary_target" "$target"
      changed=true
    fi
  fi
  if ! grep -q '^POSTGRES_OWNER_USER=' "$target"; then
    legacy_user=$(sed -n 's/^POSTGRES_USER=//p' "$target" | head -n 1)
    legacy_password=$(sed -n 's/^POSTGRES_PASSWORD=//p' "$target" | head -n 1)
    echo "POSTGRES_OWNER_USER=${legacy_user:-tekdocs_owner}" >> "$target"
    echo "POSTGRES_OWNER_PASSWORD=${legacy_password:-$(openssl rand -hex 32)}" >> "$target"
    changed=true
  fi
  if ! grep -q '^POSTGRES_RUNTIME_USER=' "$target"; then
    echo "POSTGRES_RUNTIME_USER=tekdocs_runtime" >> "$target"
    echo "POSTGRES_RUNTIME_PASSWORD=$(openssl rand -hex 32)" >> "$target"
    changed=true
  fi
  if [ "$changed" = true ]; then
    echo "Added missing database-role or bootstrap settings to $target without changing existing values"
  else
    echo "$target already contains the required generated secrets; leaving it unchanged"
  fi
  exit 0
fi

umask 077
postgres_owner_password="$(openssl rand -hex 32)"
postgres_runtime_password="$(openssl rand -hex 32)"
django_secret="$(openssl rand -base64 48 | tr -d '\n')"
master_key="$(openssl rand -base64 32 | tr -d '\n')"
signing_key="$(generate_url_safe_32_byte_key)"
bootstrap_token="$(openssl rand -base64 32 | tr -d '\n')"

{
  echo "COMPOSE_PROJECT_NAME=tekdocs"
  echo "POSTGRES_DB=tekdocs"
  echo "POSTGRES_OWNER_USER=tekdocs_owner"
  echo "POSTGRES_OWNER_PASSWORD=$postgres_owner_password"
  echo "POSTGRES_RUNTIME_USER=tekdocs_runtime"
  echo "POSTGRES_RUNTIME_PASSWORD=$postgres_runtime_password"
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
