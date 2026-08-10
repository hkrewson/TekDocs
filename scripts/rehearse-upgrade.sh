#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
baseline_ref=${TEKDOCS_UPGRADE_FROM_REF:-147d00c}
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-upgrade.XXXXXX")
baseline_directory="$work_directory/baseline"
environment_file="$work_directory/upgrade.env"
project_name="tekdocs_upgrade_$$"
test_email="upgrade-owner-$$@example.invalid"
test_password=$(openssl rand -base64 36 | tr -d '\n')

baseline_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$baseline_directory/compose.yml" -f "$baseline_directory/compose.test.yml" "$@"
}

current_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  exit_status=$?
  if [ "$exit_status" -ne 0 ]; then
    echo "Upgrade rehearsal failed; migration and backend logs follow" >&2
    current_compose logs --no-color migrate backend >&2 || true
  fi
  current_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
  exit "$exit_status"
}
trap cleanup EXIT HUP INT TERM

git -C "$repository_root" cat-file -e "$baseline_ref^{commit}"
mkdir -p "$baseline_directory"
git -C "$repository_root" archive "$baseline_ref" | tar -x -C "$baseline_directory"
"$baseline_directory/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
} >> "$environment_file"

baseline_version=$(tr -d '[:space:]' < "$baseline_directory/VERSION")
current_version=$(tr -d '[:space:]' < "$repository_root/VERSION")
if [ "$baseline_version" != "0.1.3" ]; then
  echo "Upgrade rehearsal expected baseline 0.1.3, found $baseline_version" >&2
  exit 1
fi
if [ "$current_version" = "$baseline_version" ]; then
  echo "Upgrade rehearsal requires a version newer than $baseline_version" >&2
  exit 1
fi

echo "Starting isolated TekDocs $baseline_version database"
baseline_compose up -d --build --wait backend
baseline_compose exec -T \
  -e UPGRADE_TEST_EMAIL="$test_email" \
  -e UPGRADE_TEST_PASSWORD="$test_password" \
  backend python manage.py shell -c '
import os
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import generate_totp_secret
from apps.accounts.bootstrap import bootstrap_owner
from apps.accounts.mfa_storage import encrypt_mfa_value
from apps.core.models import AuditEvent, Entity, Organization

result = bootstrap_owner(
    tenant_name="Upgrade Rehearsal MSP",
    owner_email=os.environ["UPGRADE_TEST_EMAIL"],
    owner_display_name="Upgrade Rehearsal Owner",
    password=os.environ["UPGRADE_TEST_PASSWORD"],
)
Authenticator.objects.create(
    user=result.owner,
    type=Authenticator.Type.TOTP,
    data={"secret": encrypt_mfa_value(generate_totp_secret())},
)
AuditEvent.objects.create(
    tenant=result.tenant,
    actor=result.owner,
    action="upgrade.fixture_created",
    metadata={},
)
anchor = Entity.objects.create(
    tenant=result.tenant,
    entity_type="organization",
    display_name="Preserved Client",
)
Organization.objects.create(tenant=result.tenant, entity=anchor)
print("Baseline identity fixture created")
'

baseline_compose down --remove-orphans

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
echo "Applying TekDocs $current_version to the preserved database"
current_compose up -d --build --wait backend
current_compose run --rm \
  -e UPGRADE_TEST_EMAIL="$test_email" \
  -e UPGRADE_TEST_PASSWORD="$test_password" \
  migrate python manage.py shell -c '
import os
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from apps.accounts.mfa_storage import PREFIX, decrypt_mfa_value
from apps.accounts.models import BuiltInRole, OrganizationAccessAssignment, TenantMembership, User
from apps.core.models import AuditEvent, CustomFieldDefinition, CustomFieldDefinitionVersion, EntityLink, InstallationState, Location, Organization, OrganizationAccessMode, OrganizationClassification, Site, Tenant

email = os.environ["UPGRADE_TEST_EMAIL"]
owner = User.objects.get(email=email)
state = InstallationState.objects.get(pk=InstallationState.SINGLETON_ID)
authenticator = Authenticator.objects.get(user=owner, type=Authenticator.Type.TOTP)
encrypted_secret = authenticator.data["secret"]

assert state.is_bootstrapped
assert state.owner_id == owner.id
assert state.tenant_id == Tenant.objects.get(slug="upgrade-rehearsal-msp").id
assert owner.display_name == "Upgrade Rehearsal Owner"
assert owner.check_password(os.environ["UPGRADE_TEST_PASSWORD"])
assert EmailAddress.objects.get(user=owner, email=email, primary=True, verified=True)
owner_membership = TenantMembership.scoped.for_tenant(state.tenant).get(user=owner)
assert owner_membership.role == BuiltInRole.READ_ONLY
assert encrypted_secret.startswith(PREFIX)
assert decrypt_mfa_value(encrypted_secret)
assert AuditEvent.objects.filter(action="installation.owner_bootstrapped", actor=owner).count() == 1
assert AuditEvent.objects.filter(action="upgrade.fixture_created", actor=owner, metadata={}).count() == 1
preserved_organization = Organization.scoped.for_tenant(state.tenant).get(entity__display_name="Preserved Client")
assert preserved_organization.legal_name == ""
assert preserved_organization.website == ""
assert preserved_organization.access_mode == OrganizationAccessMode.ALL_AUTHORIZED
OrganizationClassification.objects.create(
    tenant=state.tenant,
    organization=preserved_organization,
    kind="client",
)
assert OrganizationClassification.scoped.for_tenant(state.tenant).filter(
    organization=preserved_organization,
    kind="client",
).count() == 1
assert Site.scoped.for_tenant(state.tenant).count() == 0
assert Location.scoped.for_tenant(state.tenant).count() == 0
assert CustomFieldDefinition.scoped.for_tenant(state.tenant).count() == 0
assert CustomFieldDefinitionVersion.scoped.for_tenant(state.tenant).count() == 0
assert EntityLink.scoped.for_tenant(state.tenant).count() == 0
assert OrganizationAccessAssignment.scoped.for_tenant(state.tenant).count() == 0
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(
        "SELECT to_regclass(%s), to_regclass(%s), to_regclass(%s), to_regclass(%s), to_regclass(%s), to_regclass(%s), to_regclass(%s), to_regprocedure(%s), to_regprocedure(%s), to_regprocedure(%s), to_regprocedure(%s), to_regprocedure(%s), EXISTS (SELECT 1 FROM pg_constraint WHERE conname = %s), EXISTS (SELECT 1 FROM pg_constraint WHERE conname = %s)",
        [
            "core_organizationclassification",
            "core_site",
            "core_location",
            "core_customfielddefinition",
            "core_customfielddefinitionversion",
            "core_entitylink",
            "accounts_organizationaccessassignment",
            "tekdocs_validate_organization_classification_scope()",
            "tekdocs_validate_location_scope()",
            "tekdocs_validate_entity_custom_fields()",
            "tekdocs_validate_entity_link_scope()",
            "tekdocs_validate_organization_access_assignment()",
            "organization_access_mode_valid",
            "tenant_membership_role_valid",
        ],
    )
    classification_table, site_table, location_table, definition_table, version_table, entity_link_table, assignment_table, guard_function, location_guard, custom_field_guard, entity_link_guard, assignment_guard, access_mode_constraint, membership_role_constraint = cursor.fetchone()
assert classification_table == "core_organizationclassification"
assert site_table == "core_site"
assert location_table == "core_location"
assert definition_table == "core_customfielddefinition"
assert version_table == "core_customfielddefinitionversion"
assert entity_link_table == "core_entitylink"
assert assignment_table == "accounts_organizationaccessassignment"
assert guard_function == "tekdocs_validate_organization_classification_scope()"
assert location_guard == "tekdocs_validate_location_scope()"
assert custom_field_guard == "tekdocs_validate_entity_custom_fields()"
assert entity_link_guard == "tekdocs_validate_entity_link_scope()"
assert assignment_guard == "tekdocs_validate_organization_access_assignment()"
assert access_mode_constraint
assert membership_role_constraint
print("Upgraded identity and authentication invariants verified")
'
current_compose exec -T backend python manage.py check
current_compose exec -T backend python manage.py makemigrations --check --dry-run

echo "Upgrade rehearsal passed: $baseline_version -> $current_version"
