#!/usr/bin/env bash
set -Eeuo pipefail

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
invocation_directory=$PWD
environment_file="$repository_root/.env"
operator_config_file="$repository_root/.tekdocs-update.env"
saved_backup_root=
saved_recovery_key=
if [[ -e "$operator_config_file" ]]; then
  [[ -f "$operator_config_file" && -r "$operator_config_file" ]] || {
    echo "TekDocs production update refused: operator configuration is not a readable file: $operator_config_file" >&2
    exit 1
  }
  saved_backup_root=$(sed -n 's/^TEKDOCS_UPDATE_BACKUP_ROOT=//p' "$operator_config_file" | tail -n 1)
  saved_recovery_key=$(sed -n 's/^TEKDOCS_UPDATE_RECOVERY_KEY_FILE=//p' "$operator_config_file" | tail -n 1)
fi
backup_root=${TEKDOCS_BACKUP_ROOT:-$saved_backup_root}
recovery_key=${TEKDOCS_RECOVERY_KEY_FILE:-$saved_recovery_key}
secret_directory=
use_traefik=true
use_bootstrap_secret=false
skip_backup=false
application_stopped=false
backend_repository=ghcr.io/hkrewson/tekdocs-backend
frontend_repository=ghcr.io/hkrewson/tekdocs-frontend

usage() {
  cat <<'EOF'
Safely update a running TekDocs production installation.

Normal update:
  scripts/update-production.sh \
    --backup-root DIRECTORY \
    --recovery-key FILE

  --backup-root is a parent directory for a new timestamped encrypted backup.
  --recovery-key is an existing TekDocs recovery-key file kept separately from
  both the backup directory and the deployment secret directory.

Example:
  scripts/update-production.sh \
    --backup-root /path/to/tekdocs-backups \
    --recovery-key /separate/path/tekdocs-recovery.key

If no recovery key exists, create one once and retain a separate copy:
  scripts/generate-recovery-key.sh /separate/path/tekdocs-recovery.key

Update after creating a verified external VM or volume snapshot:
  scripts/update-production.sh --skip-backup

Optional arguments:
    [--env-file FILE] \
    [--secret-directory DIRECTORY] \
    [--without-traefik] \
    [--with-bootstrap-secret]

Traefik is enabled by default. SMTP and OIDC overlays are detected from secret files.
TEKDOCS_BACKUP_ROOT and TEKDOCS_RECOVERY_KEY_FILE may supply the two backup paths.
The first complete backup configuration is saved in the ignored .tekdocs-update.env file.
The update pulls the public GHCR images for the checked-out commit, verifies their
embedded revision labels, deploys immutable digests, and records those digests in .env.
EOF
}

fail() {
  echo "TekDocs production update refused: $*" >&2
  exit 1
}

resolve_digest_reference() {
  repository=$1
  tagged_reference=$2
  digest_reference=$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$tagged_reference" \
    | awk -v prefix="$repository@sha256:" 'index($0, prefix) == 1 {print; exit}')
  [[ "$digest_reference" == "$repository@sha256:"* ]] || fail "the registry digest could not be resolved for $tagged_reference"
  digest=${digest_reference#*@sha256:}
  [[ ${#digest} -eq 64 && "$digest" != *[!0-9a-f]* ]] || fail "the registry returned an invalid digest for $tagged_reference"
  printf '%s\n' "$digest_reference"
}

persist_environment_value() {
  name=$1
  value=$2
  temporary=$(mktemp "$environment_directory/.tekdocs-env.XXXXXX")
  awk -v name="$name" -v value="$value" '
    BEGIN { replaced = 0 }
    index($0, name "=") == 1 {
      if (!replaced) print name "=" value
      replaced = 1
      next
    }
    { print }
    END { if (!replaced) print name "=" value }
  ' "$environment_file" > "$temporary"
  chmod 0600 "$temporary"
  mv "$temporary" "$environment_file"
}

argument_error() {
  echo "TekDocs production update needs more information: $*" >&2
  echo >&2
  usage >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --backup-root)
      (($# >= 2)) || argument_error "--backup-root must be followed by a directory path"
      backup_root=${2:-}
      shift 2
      ;;
    --recovery-key)
      (($# >= 2)) || argument_error "--recovery-key must be followed by a recovery-key file path"
      recovery_key=${2:-}
      shift 2
      ;;
    --env-file)
      (($# >= 2)) || argument_error "--env-file must be followed by an environment-file path"
      environment_file=${2:-}
      shift 2
      ;;
    --secret-directory)
      (($# >= 2)) || argument_error "--secret-directory must be followed by a directory path"
      secret_directory=${2:-}
      shift 2
      ;;
    --without-traefik)
      use_traefik=false
      shift
      ;;
    --with-bootstrap-secret)
      use_bootstrap_secret=true
      shift
      ;;
    --skip-backup)
      skip_backup=true
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

if [[ "$skip_backup" != true ]]; then
  if [[ -z "$backup_root" && -z "$recovery_key" ]]; then
    argument_error "provide both backup paths, or use --skip-backup after a verified external snapshot"
  fi
  [[ -n "$backup_root" ]] || argument_error "--backup-root identifies where the encrypted backup will be created"
  [[ -n "$recovery_key" ]] || argument_error "--recovery-key identifies the existing key required to restore that backup"
fi

if [[ "$environment_file" != /* ]]; then
  environment_file="$invocation_directory/$environment_file"
fi
if [[ -n "$backup_root" && "$backup_root" != /* ]]; then
  backup_root="$invocation_directory/$backup_root"
fi
if [[ -n "$recovery_key" && "$recovery_key" != /* ]]; then
  recovery_key="$invocation_directory/$recovery_key"
fi

for command_name in curl docker git; do
  command -v "$command_name" >/dev/null 2>&1 || fail "$command_name is required"
done

[[ -f "$environment_file" ]] || fail "environment file not found: $environment_file"
environment_file=$(CDPATH= cd -- "$(dirname -- "$environment_file")" && pwd -P)/$(basename -- "$environment_file")
environment_directory=$(dirname -- "$environment_file")

if [[ -z "$secret_directory" ]]; then
  secret_directory=$(sed -n 's/^TEKDOCS_SECRET_DIRECTORY=//p' "$environment_file" | head -n 1)
fi
[[ -n "$secret_directory" ]] || fail "TEKDOCS_SECRET_DIRECTORY is not set in the environment file"
if [[ "$secret_directory" != /* ]]; then
  secret_directory="$environment_directory/$secret_directory"
fi
[[ -d "$secret_directory" ]] || fail "secret directory not found: $secret_directory"
secret_directory=$(CDPATH= cd -- "$secret_directory" && pwd -P)

if [[ "$skip_backup" != true ]]; then
  [[ -r "$recovery_key" ]] || fail "recovery key is not readable: $recovery_key"
  mkdir -p "$backup_root"
  backup_root=$(CDPATH= cd -- "$backup_root" && pwd -P)
  recovery_key=$(CDPATH= cd -- "$(dirname -- "$recovery_key")" && pwd -P)/$(basename -- "$recovery_key")

  operator_config_existed=false
  [[ -e "$operator_config_file" ]] && operator_config_existed=true
  umask 077
  operator_config_temporary=$(mktemp "$repository_root/.tekdocs-update.env.XXXXXX")
  {
    printf 'TEKDOCS_UPDATE_BACKUP_ROOT=%s\n' "$backup_root"
    printf 'TEKDOCS_UPDATE_RECOVERY_KEY_FILE=%s\n' "$recovery_key"
  } > "$operator_config_temporary"
  chmod 0600 "$operator_config_temporary"
  mv "$operator_config_temporary" "$operator_config_file"
  if [[ "$operator_config_existed" != true ]]; then
    echo "Saved production-update paths in $operator_config_file"
  fi
fi

compose=(
  docker compose
  --env-file "$environment_file"
  -f "$repository_root/compose.yml"
  -f "$repository_root/compose.production.yml"
  -f "$repository_root/compose.secret-files.yml"
)
if [[ -f "$secret_directory/email_host_password" ]]; then
  compose+=(-f "$repository_root/compose.smtp-secret.yml")
fi
if [[ -f "$secret_directory/oidc_client_secret" ]]; then
  compose+=(-f "$repository_root/compose.oidc-secret.yml")
fi
if [[ "$use_bootstrap_secret" == true ]]; then
  [[ -f "$secret_directory/bootstrap_token" ]] || fail "bootstrap-token file not found"
  compose+=(-f "$repository_root/compose.bootstrap-secret.yml")
fi
if [[ "$use_traefik" == true ]]; then
  compose+=(-f "$repository_root/compose.traefik.yml")
fi

on_error() {
  status=$?
  echo "TekDocs production update failed." >&2
  if [[ "$application_stopped" == true ]]; then
    echo "Application services are stopped. Inspect the migration and runtime logs before recovery." >&2
    "${compose[@]}" logs --no-color --tail=120 migrate backend worker scheduler >&2 || true
  fi
  exit "$status"
}
trap on_error ERR

cd "$repository_root"
[[ -z "$(git status --porcelain)" ]] || fail "the Git working tree is not clean"
git rev-parse --verify '@{upstream}' >/dev/null 2>&1 || fail "the current branch has no upstream"

"${compose[@]}" config --quiet
[[ -n "$("${compose[@]}" ps -q db)" ]] || fail "the production database is not running"
[[ -n "$("${compose[@]}" ps -q backend)" ]] || fail "the production backend is not running"

previous_commit=$(git rev-parse HEAD)
previous_version=$(tr -d '[:space:]' < VERSION)
backup_output=

if [[ "$skip_backup" == true ]]; then
  echo "Skipping TekDocs backup because --skip-backup was explicitly supplied."
else
  timestamp=$(date -u '+%Y%m%d-%H%M%S')
  backup_output="$backup_root/tekdocs-${previous_version}-${timestamp}"
  "$repository_root/scripts/tekdocs-backup.sh" \
    --env-file "$environment_file" \
    --secret-directory "$secret_directory" \
    --key-file "$recovery_key" \
    --output "$backup_output"
fi

echo "Fetching the configured upstream branch"
git fetch --prune
git merge --ff-only '@{upstream}'

current_commit=$(git rev-parse HEAD)
commit_tag="sha-$current_commit"
backend_tagged_reference="$backend_repository:$commit_tag"
frontend_tagged_reference="$frontend_repository:$commit_tag"

echo "Pulling validated production images for commit $current_commit"
docker pull "$backend_tagged_reference"
docker pull "$frontend_tagged_reference"

backend_revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$backend_tagged_reference")
frontend_revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$frontend_tagged_reference")
[[ "$backend_revision" == "$current_commit" ]] || fail "the backend image revision does not match the checked-out commit"
[[ "$frontend_revision" == "$current_commit" ]] || fail "the frontend image revision does not match the checked-out commit"

TEKDOCS_BACKEND_IMAGE=$(resolve_digest_reference "$backend_repository" "$backend_tagged_reference")
TEKDOCS_FRONTEND_IMAGE=$(resolve_digest_reference "$frontend_repository" "$frontend_tagged_reference")
export TEKDOCS_BACKEND_IMAGE TEKDOCS_FRONTEND_IMAGE
compose+=(-f "$repository_root/compose.images.yml")

"${compose[@]}" config --quiet
echo "Resolved backend image: $TEKDOCS_BACKEND_IMAGE"
echo "Resolved frontend image: $TEKDOCS_FRONTEND_IMAGE"

echo "Stopping application services for the migration boundary"
"${compose[@]}" stop frontend worker scheduler backend
application_stopped=true

echo "Applying database migrations"
"${compose[@]}" run --rm migrate

echo "Starting the updated installation"
"${compose[@]}" up -d --remove-orphans

public_url=$(sed -n 's/^TEKDOCS_PUBLIC_URL=//p' "$environment_file" | head -n 1)
if [[ -z "$public_url" ]]; then
  domain=$(sed -n 's/^TEKDOCS_DOMAIN=//p' "$environment_file" | head -n 1)
  [[ -n "$domain" ]] || fail "TEKDOCS_PUBLIC_URL or TEKDOCS_DOMAIN is required for health verification"
  public_url="https://$domain"
fi
health_url="${public_url%/}/api/v1/health/ready"

echo "Waiting for the public readiness endpoint"
ready=false
for _attempt in {1..12}; do
  if curl --fail --silent --show-error "$health_url" >/dev/null; then
    ready=true
    break
  fi
  sleep 5
done
if [[ "$ready" != true ]]; then
  echo "Public readiness check failed: $health_url" >&2
  false
fi

"${compose[@]}" ps
current_version=$(tr -d '[:space:]' < VERSION)
application_stopped=false
persist_environment_value TEKDOCS_BACKEND_IMAGE "$TEKDOCS_BACKEND_IMAGE"
persist_environment_value TEKDOCS_FRONTEND_IMAGE "$TEKDOCS_FRONTEND_IMAGE"
trap - ERR

echo "TekDocs production update passed: $previous_version ($previous_commit) -> $current_version ($current_commit)"
if [[ -n "$backup_output" ]]; then
  echo "Encrypted pre-update backup: $backup_output"
fi
