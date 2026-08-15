#!/usr/bin/env bash
set -Eeuo pipefail

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
# shellcheck source=scripts/lib/production-images.sh
source "$repository_root/scripts/lib/production-images.sh"

invocation_directory=$PWD
environment_file="$repository_root/.env"
domain=
secret_directory=
proxy_network=proxy
traefik_entrypoint=http
time_zone=UTC
mode=install
resume=false
use_traefik=true
skip_public_check=false
permission_image=postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193

usage() {
  cat <<'EOF'
Prepare and start a new TekDocs production installation.

Initial setup:
  scripts/setup-production.sh \
    --domain docs.example.com \
    --secret-directory /absolute/path/to/tekdocs-secrets \
    [--timezone America/Chicago] \
    [--proxy-network proxy] \
    [--traefik-entrypoint http]

Resume an interrupted initial setup without replacing secrets:
  scripts/setup-production.sh --resume [--env-file .env]

After creating the first owner, enrolling MFA, and saving recovery codes:
  scripts/setup-production.sh --finalize [--env-file .env]

Optional:
  --without-traefik       Publish the frontend port instead of using the Traefik overlay.
  --skip-public-check     Skip only the external HTTPS readiness request.

The script creates file-only production secrets, pins the tested GHCR images for
the checked-out commit, validates Compose, starts the stack, and verifies readiness.
It never replaces an existing production secret set.
EOF
}

fail() {
  echo "TekDocs production setup refused: $*" >&2
  exit 1
}

argument_error() {
  echo "TekDocs production setup needs more information: $*" >&2
  echo >&2
  usage >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --domain)
      (($# >= 2)) || argument_error "--domain must be followed by a hostname"
      domain=${2:-}
      shift 2
      ;;
    --secret-directory)
      (($# >= 2)) || argument_error "--secret-directory must be followed by an absolute path"
      secret_directory=${2:-}
      shift 2
      ;;
    --timezone)
      (($# >= 2)) || argument_error "--timezone must be followed by an IANA time-zone name"
      time_zone=${2:-}
      shift 2
      ;;
    --proxy-network)
      (($# >= 2)) || argument_error "--proxy-network must be followed by a Docker network name"
      proxy_network=${2:-}
      shift 2
      ;;
    --traefik-entrypoint)
      (($# >= 2)) || argument_error "--traefik-entrypoint must be followed by a Traefik entrypoint"
      traefik_entrypoint=${2:-}
      shift 2
      ;;
    --env-file)
      (($# >= 2)) || argument_error "--env-file must be followed by a file path"
      environment_file=${2:-}
      shift 2
      ;;
    --resume)
      mode=install
      resume=true
      shift
      ;;
    --finalize)
      mode=finalize
      shift
      ;;
    --without-traefik)
      use_traefik=false
      shift
      ;;
    --skip-public-check)
      skip_public_check=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      argument_error "unknown argument: $1"
      ;;
  esac
done

for command_name in curl docker git openssl; do
  command -v "$command_name" >/dev/null 2>&1 || fail "$command_name is required"
done
docker compose version >/dev/null 2>&1 || fail "Docker Compose is required"

if [[ "$environment_file" != /* ]]; then
  environment_file="$invocation_directory/$environment_file"
fi
environment_directory=$(dirname -- "$environment_file")
mkdir -p "$environment_directory"
environment_directory=$(CDPATH= cd -- "$environment_directory" && pwd -P)
environment_file="$environment_directory/$(basename -- "$environment_file")"

read_environment_value() {
  local name=$1
  sed -n "s/^${name}=//p" "$environment_file" | head -n 1
}

build_compose() {
  local include_bootstrap=$1
  compose=(
    docker compose
    --env-file "$environment_file"
    -f "$repository_root/compose.yml"
    -f "$repository_root/compose.production.yml"
    -f "$repository_root/compose.secret-files.yml"
    -f "$repository_root/compose.images.yml"
  )
  [[ -f "$secret_directory/email_host_password" ]] && compose+=(-f "$repository_root/compose.smtp-secret.yml")
  [[ -f "$secret_directory/oidc_client_secret" ]] && compose+=(-f "$repository_root/compose.oidc-secret.yml")
  [[ "$include_bootstrap" == true ]] && compose+=(-f "$repository_root/compose.bootstrap-secret.yml")
  [[ "$use_traefik" == true ]] && compose+=(-f "$repository_root/compose.traefik.yml")
}

verify_secret_set() {
  local name details
  for name in django_secret_key postgres_owner_password postgres_runtime_password tekdocs_master_key publication_signing_key; do
    [[ -f "$secret_directory/$name" ]] || fail "required secret file is missing: $secret_directory/$name"
  done
  if [[ "$mode" == install ]]; then
    [[ -f "$secret_directory/bootstrap_token" ]] || fail "bootstrap-token file is missing: $secret_directory/bootstrap_token"
  fi
  details=$(docker run --rm -v "$secret_directory:/secrets:ro" "$permission_image" sh -c '
    for file in /secrets/*; do
      [ -f "$file" ] || continue
      owner=$(stat -c "%u:%g" "$file")
      mode=$(stat -c "%a" "$file")
      [ "$owner" = "0:0" ] && [ "$mode" = "444" ] || {
        echo "$(basename "$file") $owner $mode"
        exit 1
      }
    done
  ') || fail "secret files must be owned by root:root with mode 0444${details:+ ($details)}"
}

public_readiness_check() {
  local public_url health_url ready=false
  public_url=$(read_environment_value TEKDOCS_PUBLIC_URL)
  health_url="${public_url%/}/api/v1/health/ready"
  for _attempt in {1..12}; do
    if curl --fail --silent --show-error "$health_url" >/dev/null; then
      ready=true
      break
    fi
    sleep 5
  done
  [[ "$ready" == true ]] || fail "public readiness check failed: $health_url"
}

if [[ "$mode" == finalize ]]; then
  [[ -f "$environment_file" ]] || fail "environment file not found: $environment_file"
  secret_directory=$(read_environment_value TEKDOCS_SECRET_DIRECTORY)
  [[ "$secret_directory" == /* && -d "$secret_directory" ]] || fail "TEKDOCS_SECRET_DIRECTORY must identify an existing absolute directory"
  TEKDOCS_BACKEND_IMAGE=$(read_environment_value TEKDOCS_BACKEND_IMAGE)
  TEKDOCS_FRONTEND_IMAGE=$(read_environment_value TEKDOCS_FRONTEND_IMAGE)
  export TEKDOCS_BACKEND_IMAGE TEKDOCS_FRONTEND_IMAGE
  [[ "$TEKDOCS_BACKEND_IMAGE" == "$TEKDOCS_BACKEND_REPOSITORY@sha256:"* ]] || fail "TEKDOCS_BACKEND_IMAGE is not pinned"
  [[ "$TEKDOCS_FRONTEND_IMAGE" == "$TEKDOCS_FRONTEND_REPOSITORY@sha256:"* ]] || fail "TEKDOCS_FRONTEND_IMAGE is not pinned"
  verify_secret_set
  build_compose false

  public_url=$(read_environment_value TEKDOCS_PUBLIC_URL)
  bootstrap_status=$(curl --fail --silent --show-error "${public_url%/}/api/v1/bootstrap/status")
  [[ "$bootstrap_status" == *'"bootstrap_required":false'* ]] || fail "create the first owner and complete MFA before finalizing setup"
  echo "Restarting TekDocs without the owner-bootstrap secret"
  "${compose[@]}" up -d --force-recreate --remove-orphans
  docker run --rm -v "$secret_directory:/secrets" "$permission_image" rm -f /secrets/bootstrap_token
  "${compose[@]}" config --quiet
  [[ "$skip_public_check" == true ]] || public_readiness_check
  echo "TekDocs production setup finalized; the bootstrap secret has been removed."
  exit 0
fi

if [[ "$resume" == true ]]; then
  [[ -f "$environment_file" ]] || fail "--resume requires an existing environment file"
  domain=$(read_environment_value TEKDOCS_DOMAIN)
  secret_directory=$(read_environment_value TEKDOCS_SECRET_DIRECTORY)
  proxy_network=$(read_environment_value TEKDOCS_PROXY_NETWORK)
  traefik_entrypoint=$(read_environment_value TEKDOCS_TRAEFIK_ENTRYPOINT)
  [[ -n "$proxy_network" ]] || proxy_network=proxy
  [[ -n "$traefik_entrypoint" ]] || traefik_entrypoint=http
  [[ "$secret_directory" == /* && -d "$secret_directory" ]] || fail "TEKDOCS_SECRET_DIRECTORY must identify an existing absolute directory"
  verify_secret_set
else
  [[ -n "$domain" ]] || argument_error "--domain is required for an initial setup"
  [[ "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ && "$domain" == *.* ]] \
    || fail "--domain must be a hostname without a scheme, port, path, or trailing dot"
  [[ -n "$secret_directory" ]] || argument_error "--secret-directory is required for an initial setup"
  [[ "$secret_directory" == /* ]] || fail "--secret-directory must be an absolute path"
  [[ ! -e "$environment_file" ]] || fail "environment file already exists; use --resume to retain it"
  [[ ! -e "$secret_directory" ]] || fail "secret directory already exists; use --resume to retain it"

  mkdir -m 0700 "$secret_directory"
  secret_directory=$(CDPATH= cd -- "$secret_directory" && pwd -P)
  umask 077
  openssl rand -base64 48 > "$secret_directory/django_secret_key"
  openssl rand -hex 32 > "$secret_directory/postgres_owner_password"
  openssl rand -hex 32 > "$secret_directory/postgres_runtime_password"
  openssl rand -base64 32 > "$secret_directory/tekdocs_master_key"
  openssl rand -base64 32 | tr '+/' '-_' > "$secret_directory/publication_signing_key"
  openssl rand -base64 32 > "$secret_directory/bootstrap_token"
  docker run --rm -v "$secret_directory:/secrets" "$permission_image" sh -c \
    'chown 0:0 /secrets/* && chmod 0444 /secrets/*'

  umask 077
  {
    echo "COMPOSE_PROJECT_NAME=tekdocs"
    echo "TEKDOCS_DOMAIN=$domain"
    echo "TEKDOCS_PROXY_NETWORK=$proxy_network"
    echo "TEKDOCS_TRAEFIK_ENTRYPOINT=$traefik_entrypoint"
    echo "TEKDOCS_SECRET_DIRECTORY=$secret_directory"
    echo "POSTGRES_DB=tekdocs"
    echo "POSTGRES_OWNER_USER=tekdocs_owner"
    echo "POSTGRES_RUNTIME_USER=tekdocs_runtime"
    echo "DJANGO_ALLOWED_HOSTS=$domain,localhost,127.0.0.1,backend,tekdocs-backend,frontend"
    echo "DJANGO_CSRF_TRUSTED_ORIGINS=https://$domain"
    echo "TEKDOCS_PUBLIC_URL=https://$domain"
    echo "TEKDOCS_ALLOW_INSECURE_PUBLIC_URL=false"
    echo "TEKDOCS_ALLOW_DEVELOPMENT_IMAGE=false"
    echo "TEKDOCS_PUBLICATION_RETIRED_KEY_FINGERPRINTS="
    echo "TEKDOCS_RDAP_BOOTSTRAP_URL=https://data.iana.org/rdap/dns.json"
    echo "TEKDOCS_DOH_URL="
    echo "TEKDOCS_OIDC_PROVIDER_ID="
    echo "TEKDOCS_OIDC_PROVIDER_NAME="
    echo "TEKDOCS_OIDC_DISCOVERY_URL="
    echo "TEKDOCS_OIDC_CLIENT_ID="
    echo "INVITATION_TTL_HOURS=168"
    echo "PASSWORD_RESET_TIMEOUT_SECONDS=3600"
    echo "MAILPIT_UI_PORT=8025"
    echo "EMAIL_HOST=mailpit"
    echo "EMAIL_PORT=1025"
    echo "EMAIL_HOST_USER="
    echo "EMAIL_USE_TLS=false"
    echo "EMAIL_USE_SSL=false"
    echo "EMAIL_TIMEOUT=10"
    echo "DEFAULT_FROM_EMAIL=TekDocs <noreply@$domain>"
    echo "TEKDOCS_ALLOW_INSECURE_SMTP=true"
    echo "SECURE_SSL_REDIRECT=true"
    echo "TZ=$time_zone"
  } > "$environment_file"
  chmod 0600 "$environment_file"
  verify_secret_set
fi

[[ -n "$domain" ]] || fail "TEKDOCS_DOMAIN is missing from the environment file"
[[ -z "$(git -C "$repository_root" status --porcelain)" ]] || fail "the Git working tree is not clean; production images correspond to committed source"
if [[ "$use_traefik" == true ]]; then
  docker network inspect "$proxy_network" >/dev/null 2>&1 || fail "Traefik network does not exist: $proxy_network"
fi

current_commit=$(git -C "$repository_root" rev-parse HEAD)
tekdocs_resolve_production_images "$current_commit"
TEKDOCS_BACKEND_IMAGE=$TEKDOCS_RESOLVED_BACKEND_IMAGE
TEKDOCS_FRONTEND_IMAGE=$TEKDOCS_RESOLVED_FRONTEND_IMAGE
export TEKDOCS_BACKEND_IMAGE TEKDOCS_FRONTEND_IMAGE
tekdocs_persist_environment_value "$environment_file" TEKDOCS_BACKEND_IMAGE "$TEKDOCS_BACKEND_IMAGE"
tekdocs_persist_environment_value "$environment_file" TEKDOCS_FRONTEND_IMAGE "$TEKDOCS_FRONTEND_IMAGE"

build_compose true
"${compose[@]}" config --quiet
echo "Starting TekDocs with the temporary owner-bootstrap boundary"
"${compose[@]}" pull
"${compose[@]}" up -d --wait --remove-orphans

echo "Verifying the frontend-to-backend route"
"${compose[@]}" exec -T frontend wget -q -O /dev/null \
  --header="Host: $domain" \
  --header='X-Forwarded-Proto: https' \
  http://tekdocs-backend:8000/api/v1/health/ready
[[ "$skip_public_check" == true ]] || public_readiness_check

"${compose[@]}" ps
echo
echo "Deployment token:"
"${compose[@]}" exec -T backend cat /run/secrets/bootstrap_token
echo
echo "Create the first owner at https://$domain, enroll MFA, and save the recovery codes."
echo "Then run: scripts/setup-production.sh --finalize --env-file $environment_file"
