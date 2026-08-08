#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-clean-install.XXXXXX")
environment_file="$work_directory/clean-install.env"
project_name="tekdocs_clean_install_$$"
test_port=$((34000 + ($$ % 1000)))
mailpit_port=$((8400 + ($$ % 1000)))

clean_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  clean_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=$test_port"
  echo "MAILPIT_UI_PORT=$mailpit_port"
} >> "$environment_file"

release_version=$(tr -d '[:space:]' < "$repository_root/VERSION")
echo "Starting isolated clean install of TekDocs $release_version"
clean_compose up -d --build --wait

readiness=$(curl --fail --silent "http://localhost:$test_port/api/v1/health/ready")
case "$readiness" in
  *'"status":"ok"'*'"database":"ready"'*'"version":"'"$release_version"'"'*) ;;
  *)
    echo "Clean-install readiness response did not match the release contract" >&2
    exit 1
    ;;
esac
curl --fail --silent "http://127.0.0.1:$mailpit_port/readyz" >/dev/null

clean_compose exec -T backend python manage.py migrate --check
clean_compose exec -T backend python manage.py makemigrations --check --dry-run
clean_compose exec -T backend python manage.py shell -c '
from apps.accounts.models import BuiltInRole, TenantMembership, User
from apps.core.models import AuditEvent, CustomFieldDefinition, CustomFieldDefinitionVersion, EntityLink, InstallationState, Organization, OrganizationAccessMode, Tenant

state = InstallationState.objects.get(pk=InstallationState.SINGLETON_ID)
assert not state.is_bootstrapped
assert state.owner_id is None
assert state.tenant_id is None
assert Tenant.objects.count() == 0
assert User.objects.count() == 0
assert TenantMembership.objects.count() == 0
assert AuditEvent.objects.count() == 0
assert CustomFieldDefinition.objects.count() == 0
assert CustomFieldDefinitionVersion.objects.count() == 0
assert EntityLink.objects.count() == 0
assert TenantMembership._meta.get_field("role").get_default() == BuiltInRole.READ_ONLY
assert Organization._meta.get_field("access_mode").get_default() == OrganizationAccessMode.ALL_AUTHORIZED
print("Fresh installation state verified")
'

echo "Clean-install rehearsal passed for TekDocs $release_version"
