#!/usr/bin/env bash
set -Eeuo pipefail

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
# shellcheck source=scripts/lib/production-images.sh
source "$repository_root/scripts/lib/production-images.sh"
# shellcheck source=scripts/lib/production-release.sh
source "$repository_root/scripts/lib/production-release.sh"
invocation_directory=$PWD
environment_file="$repository_root/.env"
operator_config_file="$repository_root/.tekdocs-update.env"
backup_root=${TEKDOCS_BACKUP_ROOT:-}
recovery_key=${TEKDOCS_RECOVERY_KEY_FILE:-}
secret_directory=
use_traefik=true
use_bootstrap_secret=false
skip_backup=false
application_stopped=false
release=
release_directory=
mode=
update_controls=false
argument_count=$#

brief_usage() {
  cat <<'EOF'
TekDocs production updater

Nothing was changed. Choose what you want to do:
  scripts/update-production.sh --check          Show the installed and latest releases
  scripts/update-production.sh --list-releases  Show published release tags
  scripts/update-production.sh --latest         Install the latest published stable release
  scripts/update-production.sh --release TAG    Install one published release, such as v0.9.18

Run scripts/update-production.sh --help for requirements and all options.
EOF
}

usage() {
  cat <<'EOF'
Safely update a running TekDocs production installation.

Common commands:
  scripts/update-production.sh --check
      Show the tooling version, recorded deployed release and latest published release.

  scripts/update-production.sh --list-releases
      List stable application tags that have a companion CI receipt tag.

  scripts/update-production.sh --latest
      Update to the latest published stable release after validating its receipt.

  scripts/update-production.sh --release vMAJOR.MINOR.PATCH
      Update to an explicitly selected published release.

Update requirements:
  A clean tooling checkout, a running production database and backend, Docker,
  Git, curl, the production .env and secret directory, and either:

  --backup-root DIRECTORY --recovery-key FILE
      Create a timestamped encrypted backup before changing services. The key
      must be retained separately from the backup and deployment secrets.

  --skip-backup
      Continue only after creating and verifying an external VM or volume snapshot.

Examples:
  scripts/update-production.sh --latest \
    --backup-root /path/to/tekdocs-backups \
    --recovery-key /separate/path/tekdocs-recovery.key

  scripts/update-production.sh --release v0.9.18

Options:
  --check                         Read-only update availability check
  --list-releases                 Read-only published release list
  --latest                        Select the newest published stable release
  --release TAG                   Select an exact vMAJOR.MINOR.PATCH release
  --upstream                      Advanced legacy branch update mode
  --backup-root DIRECTORY         Parent directory for the new encrypted backup
  --recovery-key FILE             Existing recovery-key file
  --skip-backup                   Use an already verified external snapshot
  --env-file FILE                 Production environment file
  --secret-directory DIRECTORY    Production secret-files directory
  --without-traefik               Exclude the Traefik overlay
  --with-bootstrap-secret         Include the bootstrap-secret overlay
  -h, --help                      Show this help

Create a recovery key once, if needed:
  scripts/generate-recovery-key.sh /separate/path/tekdocs-recovery.key

Release mode retrieves the CI receipt (or uses a historical local receipt), checks the exact tag commit,
image revisions and digests. It uses the release Compose files without changing
the tooling checkout. Existing backup settings still apply.
The first complete backup configuration is saved in ignored .tekdocs-update.env.
TEKDOCS_BACKUP_ROOT and TEKDOCS_RECOVERY_KEY_FILE may supply those paths.
Calling the updater with backup options but no selector preserves legacy upstream
mode with a deprecation warning; use --upstream explicitly instead.
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

set_mode() {
  local requested=$1
  [[ -z "$mode" ]] || argument_error "$requested cannot be combined with the selected $mode mode"
  mode=$requested
}

while (($#)); do
  case "$1" in
    --release)
      (($# >= 2)) || argument_error "--release requires a version tag"
      [[ -n "$2" ]] || argument_error "--release requires a version tag"
      set_mode release
      release=$2
      shift 2
      ;;
    --latest)
      set_mode latest
      shift
      ;;
    --list-releases)
      set_mode list-releases
      shift
      ;;
    --check)
      set_mode check
      shift
      ;;
    --upstream)
      set_mode upstream
      shift
      ;;
    --backup-root)
      (($# >= 2)) || argument_error "--backup-root must be followed by a directory path"
      update_controls=true
      backup_root=${2:-}
      shift 2
      ;;
    --recovery-key)
      (($# >= 2)) || argument_error "--recovery-key must be followed by a recovery-key file path"
      update_controls=true
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
      update_controls=true
      secret_directory=${2:-}
      shift 2
      ;;
    --without-traefik)
      update_controls=true
      use_traefik=false
      shift
      ;;
    --with-bootstrap-secret)
      update_controls=true
      use_bootstrap_secret=true
      shift
      ;;
    --skip-backup)
      update_controls=true
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

if [[ -z "$mode" ]]; then
  if ((argument_count == 0)); then
    brief_usage
    exit 0
  fi
  mode=upstream
  echo "Warning: implicit upstream mode is deprecated; use --upstream explicitly." >&2
fi

if [[ "$mode" == list-releases || "$mode" == check ]]; then
  [[ "$update_controls" == false ]] || argument_error "$mode is read-only and cannot be combined with update options"
  catalog=$(tekdocs_discover_published_releases "$repository_root") || fail "published release tags could not be read from origin"
  if [[ "$mode" == list-releases ]]; then
    echo "Published TekDocs releases (newest first):"
    while IFS=$'\t' read -r published_release _commit; do
      printf '  %s\n' "$published_release"
    done <<< "$catalog"
    echo "Each tag has a companion CI receipt; the receipt is validated when selected."
    exit 0
  fi
  latest_line=${catalog%%$'\n'*}
  latest_release=${latest_line%%$'\t'*}
  checkout_version=$(tr -d '[:space:]' < "$repository_root/VERSION")
  deployed_commit=
  if [[ "$environment_file" != /* ]]; then
    environment_file="$invocation_directory/$environment_file"
  fi
  if [[ -f "$environment_file" ]]; then
    deployed_commit=$(sed -n 's/^TEKDOCS_DEPLOYED_COMMIT=//p' "$environment_file" | head -n 1)
  fi
  deployed_release=
  if [[ "$deployed_commit" =~ ^[0-9a-f]{40}$ ]]; then
    while IFS=$'\t' read -r published_release published_commit; do
      [[ "$published_commit" == "$deployed_commit" ]] || continue
      deployed_release=$published_release
      break
    done <<< "$catalog"
  fi
  echo "TekDocs update check"
  echo "  Tooling checkout version: v$checkout_version"
  if [[ -n "$deployed_release" ]]; then
    echo "  Recorded deployed release: $deployed_release"
  elif [[ -n "$deployed_commit" ]]; then
    echo "  Recorded deployed commit: ${deployed_commit:0:12} (not a listed release)"
  else
    echo "  Recorded deployed release: not available in $environment_file"
  fi
  echo "  Latest published release: $latest_release"
  if [[ "$deployed_release" == "$latest_release" ]]; then
    echo "  Status: up to date"
  elif [[ -n "$deployed_release" ]]; then
    echo "  Status: update available ($deployed_release -> $latest_release)"
  else
    echo "  Status: deployed release could not be compared"
  fi
  echo "Run scripts/update-production.sh --latest to select it."
  exit 0
fi

if [[ "$mode" == latest ]]; then
  release=$(tekdocs_latest_published_release "$repository_root") || fail "the latest published release could not be determined from origin"
  echo "Selected latest published release: $release"
fi

if [[ "$mode" == release || "$mode" == latest ]]; then
  tekdocs_load_published_release "$repository_root" "$release" || argument_error "release has no valid reviewed image receipt: $release"
fi

if [[ "$mode" == latest ]]; then
  comparison_environment_file=$environment_file
  if [[ "$comparison_environment_file" != /* ]]; then
    comparison_environment_file="$invocation_directory/$comparison_environment_file"
  fi
  recorded_deployed_commit=
  if [[ -f "$comparison_environment_file" ]]; then
    recorded_deployed_commit=$(sed -n 's/^TEKDOCS_DEPLOYED_COMMIT=//p' "$comparison_environment_file" | head -n 1)
  fi
  if [[ "$recorded_deployed_commit" == "$TEKDOCS_RELEASE_COMMIT" ]]; then
    echo "Production is already on $release; nothing to update."
    exit 0
  fi
fi

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
[[ -n "$backup_root" ]] || backup_root=$saved_backup_root
[[ -n "$recovery_key" ]] || recovery_key=$saved_recovery_key

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
  --project-directory "$repository_root"
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
    echo "The application update did not complete. Inspect migration and runtime logs before recovery." >&2
    "${compose[@]}" logs --no-color --tail=120 migrate backend worker scheduler >&2 || true
  fi
  exit "$status"
}
trap on_error ERR
cleanup_release() {
  if [[ -n "$release_directory" ]]; then
    rm -rf -- "$release_directory"
  fi
}
trap cleanup_release EXIT

cd "$repository_root"
[[ -z "$(git status --porcelain)" ]] || fail "the Git working tree is not clean"
if [[ -z "$release" ]]; then
  git rev-parse --verify '@{upstream}' >/dev/null 2>&1 || fail "the current branch has no upstream"
fi

"${compose[@]}" config --quiet
[[ -n "$("${compose[@]}" ps -q db)" ]] || fail "the production database is not running"
[[ -n "$("${compose[@]}" ps -q backend)" ]] || fail "the production backend is not running"

previous_commit=$(git rev-parse HEAD)
previous_version=$(tr -d '[:space:]' < VERSION)
backup_output=

if [[ "$skip_backup" == true ]]; then
  backup_plan="verified external snapshot (--skip-backup)"
else
  timestamp=$(date -u '+%Y%m%d-%H%M%S')
  backup_output="$backup_root/tekdocs-${previous_version}-${timestamp}"
  backup_plan=$backup_output
fi

echo "TekDocs production update plan"
echo "  Current tooling version: v$previous_version (${previous_commit:0:12})"
if [[ -n "$release" ]]; then
  echo "  Selected release: $release"
else
  echo "  Selected source: configured upstream branch (advanced mode)"
fi
echo "  Pre-update recovery: $backup_plan"
echo "  Traefik overlay: $use_traefik"

if [[ "$skip_backup" == true ]]; then
  echo "Skipping TekDocs backup because --skip-backup was explicitly supplied."
else
  "$repository_root/scripts/tekdocs-backup.sh" \
    --env-file "$environment_file" \
    --secret-directory "$secret_directory" \
    --key-file "$recovery_key" \
    --output "$backup_output"
fi

if [[ -n "$release" ]]; then
  echo "Fetching approved release $release"
  git fetch origin "refs/tags/$release:refs/tags/$release"
  current_commit=$(git rev-parse --verify "refs/tags/$release^{commit}")
  [[ "$current_commit" == "$TEKDOCS_RELEASE_COMMIT" ]] || fail "release tag does not match its reviewed commit"
  running_backend=$("${compose[@]}" ps -q backend)
  running_commit=$(docker inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$running_backend")
  [[ "$running_commit" =~ ^[0-9a-f]{40}$ ]] || fail "running backend has no verifiable revision"
  git merge-base --is-ancestor "$running_commit" "$current_commit" || fail "release is not a forward update from the running backend; use the recovery procedure"
  release_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-release.XXXXXX")
  git archive "$current_commit" | tar -x -C "$release_directory"
  [[ "$(tr -d '[:space:]' < "$release_directory/VERSION")" == "${release#v}" ]] || fail "release version metadata does not match its tag"
  include_mailpit=false
  if grep -q TEKDOCS_MAILPIT_IMAGE "$release_directory/compose.images.yml"; then
    include_mailpit=true
    [[ -n "$TEKDOCS_RELEASE_MAILPIT" ]] || fail "release requires a reviewed Mailpit digest"
  fi
  tekdocs_resolve_production_images "$current_commit" "$include_mailpit"
  tekdocs_verify_release_images || fail "pulled images do not match the reviewed release digests"
  for index in "${!compose[@]}"; do
    case "${compose[$index]}" in
      "$repository_root"/compose*.yml)
        compose[$index]="$release_directory/${compose[$index]##*/}"
        ;;
    esac
  done
  image_compose="$release_directory/compose.images.yml"
else
  echo "Fetching the configured upstream branch"
  git fetch --prune
  git merge --ff-only '@{upstream}'
  current_commit=$(git rev-parse HEAD)
  include_mailpit=false
  grep -q TEKDOCS_MAILPIT_IMAGE "$repository_root/compose.images.yml" && include_mailpit=true
  tekdocs_resolve_production_images "$current_commit" "$include_mailpit"
  image_compose="$repository_root/compose.images.yml"
fi
TEKDOCS_BACKEND_IMAGE=$TEKDOCS_RESOLVED_BACKEND_IMAGE
TEKDOCS_FRONTEND_IMAGE=$TEKDOCS_RESOLVED_FRONTEND_IMAGE
TEKDOCS_RENDERER_IMAGE=$TEKDOCS_RESOLVED_RENDERER_IMAGE
TEKDOCS_MAILPIT_IMAGE=${TEKDOCS_RESOLVED_MAILPIT_IMAGE:-}
export TEKDOCS_BACKEND_IMAGE TEKDOCS_FRONTEND_IMAGE TEKDOCS_RENDERER_IMAGE TEKDOCS_MAILPIT_IMAGE
compose+=(-f "$image_compose")

"${compose[@]}" config --quiet
echo "Resolved backend image: $TEKDOCS_BACKEND_IMAGE"
echo "Resolved frontend image: $TEKDOCS_FRONTEND_IMAGE"
echo "Resolved diagram renderer image: $TEKDOCS_RENDERER_IMAGE"

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

if [[ -n "$release" ]]; then
  release_services=(backend worker scheduler frontend diagram-renderer)
  [[ -z "$TEKDOCS_MAILPIT_IMAGE" ]] || release_services+=(mailpit)
  for service in "${release_services[@]}"; do
    case "$service" in
      mailpit) expected_image=$TEKDOCS_MAILPIT_IMAGE ;;
      frontend) expected_image=$TEKDOCS_FRONTEND_IMAGE ;;
      diagram-renderer) expected_image=$TEKDOCS_RENDERER_IMAGE ;;
      *) expected_image=$TEKDOCS_BACKEND_IMAGE ;;
    esac
    container_id=$("${compose[@]}" ps -q "$service")
    [[ -n "$container_id" ]] || fail "updated service is not running: $service"
    actual_image=$(docker inspect --format '{{.Config.Image}}' "$container_id")
    [[ "$actual_image" == "$expected_image" ]] || fail "running service does not use the reviewed image: $service"
  done
fi

"${compose[@]}" ps
current_version=$(tr -d '[:space:]' < "${release_directory:-$repository_root}/VERSION")
application_stopped=false
tekdocs_persist_environment_value "$environment_file" TEKDOCS_BACKEND_IMAGE "$TEKDOCS_BACKEND_IMAGE"
tekdocs_persist_environment_value "$environment_file" TEKDOCS_FRONTEND_IMAGE "$TEKDOCS_FRONTEND_IMAGE"
tekdocs_persist_environment_value "$environment_file" TEKDOCS_RENDERER_IMAGE "$TEKDOCS_RENDERER_IMAGE"
if [[ -n "$TEKDOCS_MAILPIT_IMAGE" ]]; then
  tekdocs_persist_environment_value "$environment_file" TEKDOCS_MAILPIT_IMAGE "$TEKDOCS_MAILPIT_IMAGE"
fi
tekdocs_persist_environment_value "$environment_file" TEKDOCS_DEPLOYED_COMMIT "$current_commit"
trap - ERR

echo "TekDocs production update passed: $previous_version ($previous_commit) -> $current_version ($current_commit)"
if [[ -n "$backup_output" ]]; then
  echo "Encrypted pre-update backup: $backup_output"
fi
