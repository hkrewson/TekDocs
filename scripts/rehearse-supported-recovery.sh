#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-supported-recovery.XXXXXX")
source_environment="$work_directory/source.env"
restore_environment="$work_directory/restore.env"
source_secrets="$work_directory/source-secrets"
restored_secrets="$work_directory/restored-secrets"
backup_directory="$work_directory/encrypted-backup"
recovery_key="$work_directory/separate-custody.key"
wrong_key="$work_directory/wrong.key"
source_project="tekdocs_supported_backup_$$"
restore_project="tekdocs_supported_restore_$$"
fixture_password=$(openssl rand -base64 36 | tr -d '\n')

compose_for() {
  environment=$1
  secret_directory=$2
  shift 2
  TEKDOCS_SECRET_DIRECTORY="$secret_directory" docker compose --env-file "$environment" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" \
    -f "$repository_root/compose.production.yml" -f "$repository_root/compose.secret-files.yml" \
    -f "$repository_root/compose.bootstrap-secret.yml" "$@"
}
cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "Recovery rehearsal failed; retained backend diagnostics follow:" >&2
    compose_for "$restore_environment" "$restored_secrets" logs --no-color --tail 120 backend >&2 || true
  fi
  compose_for "$source_environment" "$source_secrets" down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  compose_for "$restore_environment" "$restored_secrets" down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$source_environment" >/dev/null
mkdir -m 0700 "$source_secrets"
copy_secret() {
  name=$1
  target=$2
  value=$(sed -n "s/^${name}=//p" "$source_environment" | head -n 1)
  printf '%s\n' "$value" > "$source_secrets/$target"
  chmod 0600 "$source_secrets/$target"
}
copy_secret DJANGO_SECRET_KEY django_secret_key
copy_secret POSTGRES_OWNER_PASSWORD postgres_owner_password
copy_secret POSTGRES_RUNTIME_PASSWORD postgres_runtime_password
copy_secret TEKDOCS_MASTER_KEY tekdocs_master_key
copy_secret TEKDOCS_PUBLICATION_SIGNING_KEY publication_signing_key
copy_secret TEKDOCS_BOOTSTRAP_TOKEN bootstrap_token
sed -E \
  -e 's/^COMPOSE_PROJECT_NAME=.*/COMPOSE_PROJECT_NAME='"$source_project"'/' \
  -e 's/^(DJANGO_SECRET_KEY|POSTGRES_OWNER_PASSWORD|POSTGRES_RUNTIME_PASSWORD|TEKDOCS_MASTER_KEY|TEKDOCS_PUBLICATION_SIGNING_KEY|TEKDOCS_BOOTSTRAP_TOKEN)=.*/\1=/' \
  "$source_environment" > "$source_environment.sanitized"
mv "$source_environment.sanitized" "$source_environment"
chmod 0600 "$source_environment"
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$source_environment"
sed 's/^COMPOSE_PROJECT_NAME=.*/COMPOSE_PROJECT_NAME='"$restore_project"'/' "$source_environment" > "$restore_environment"
chmod 0600 "$restore_environment"
"$repository_root/scripts/generate-recovery-key.sh" "$recovery_key" >/dev/null
"$repository_root/scripts/generate-recovery-key.sh" "$wrong_key" >/dev/null

echo "Creating representative retained state in a production-target source stack"
compose_for "$source_environment" "$source_secrets" up -d --build --wait backend
compose_for "$source_environment" "$source_secrets" exec -T \
  -e TEKDOCS_FIXTURE_MODE=create -e TEKDOCS_FIXTURE_PASSWORD="$fixture_password" \
  backend python manage.py shell < "$repository_root/scripts/compliance-monitoring-validation-fixture.py"

"$repository_root/scripts/tekdocs-backup.sh" --env-file "$source_environment" \
  --secret-directory "$source_secrets" --key-file "$recovery_key" --output "$backup_directory"
echo "Checking encrypted artifacts for plaintext deployment values"
for secret_file in "$source_secrets"/*; do
  secret_value=$(sed -n '1p' "$secret_file")
  if grep -aFq "$secret_value" "$backup_directory"/*; then
    echo "An encrypted recovery artifact disclosed a deployment secret." >&2
    exit 1
  fi
done
echo "Checking mandatory destructive confirmation"
if "$repository_root/scripts/tekdocs-restore.sh" --env-file "$restore_environment" \
  --backup "$backup_directory" --key-file "$recovery_key" \
  --secret-output "$restored_secrets" > "$work_directory/no-confirm.log" 2>&1; then
  echo "Restore proceeded without exact destructive confirmation." >&2
  exit 1
fi
grep -q 'Restore is destructive' "$work_directory/no-confirm.log"
echo "Checking separate-key authentication failure"
if "$repository_root/scripts/tekdocs-restore.sh" --env-file "$restore_environment" \
  --backup "$backup_directory" --key-file "$wrong_key" \
  --secret-output "$restored_secrets-wrong" --confirm-destroy "$restore_project" \
  > "$work_directory/wrong-key.log" 2>&1; then
  echo "Restore accepted a different recovery key." >&2
  exit 1
fi
if ! grep -Eq 'authentication failed|manifest authentication failed' "$work_directory/wrong-key.log"; then
  echo "Wrong-key failure did not use the expected value-free authentication error:" >&2
  sed -n '1,20p' "$work_directory/wrong-key.log" >&2
  exit 1
fi
[ ! -e "$restored_secrets-wrong" ]

echo "Restoring into independently named database, media, and secret custody"
"$repository_root/scripts/tekdocs-restore.sh" --env-file "$restore_environment" \
  --backup "$backup_directory" --key-file "$recovery_key" \
  --secret-output "$restored_secrets" --confirm-destroy "$restore_project"
compose_for "$restore_environment" "$restored_secrets" exec -T \
  -e TEKDOCS_FIXTURE_MODE=verify backend python manage.py shell \
  < "$repository_root/scripts/compliance-monitoring-validation-fixture.py"
for secret_file in django_secret_key postgres_owner_password postgres_runtime_password tekdocs_master_key publication_signing_key; do
  cmp "$source_secrets/$secret_file" "$restored_secrets/$secret_file"
done
echo "Supported encrypted backup, separate-key, destructive-guard, and restore rehearsal passed"
