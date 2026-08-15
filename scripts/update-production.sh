#!/usr/bin/env bash
set -Eeuo pipefail

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
invocation_directory=$PWD
environment_file="$repository_root/.env"
backup_root=${TEKDOCS_BACKUP_ROOT:-}
recovery_key=${TEKDOCS_RECOVERY_KEY_FILE:-}
secret_directory=
use_traefik=true
use_bootstrap_secret=false
skip_backup=false
application_stopped=false

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
EOF
}

fail() {
  echo "TekDocs production update refused: $*" >&2
  exit 1
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
  [[ -n "$backup_root" ]] || fail "--backup-root is required"
  [[ -n "$recovery_key" && -r "$recovery_key" ]] || fail "--recovery-key must identify a readable file"
  mkdir -p "$backup_root"
  backup_root=$(CDPATH= cd -- "$backup_root" && pwd -P)
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

"${compose[@]}" config --quiet

echo "Building updated production images while the current installation remains available"
"${compose[@]}" build

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
current_commit=$(git rev-parse HEAD)
current_version=$(tr -d '[:space:]' < VERSION)
application_stopped=false
trap - ERR

echo "TekDocs production update passed: $previous_version ($previous_commit) -> $current_version ($current_commit)"
if [[ -n "$backup_output" ]]; then
  echo "Encrypted pre-update backup: $backup_output"
fi
