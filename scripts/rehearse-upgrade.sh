#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
baseline_ref=${TEKDOCS_UPGRADE_FROM_REF:-4ce3f92d4d16fbfcd629dfe407052e8c2fca6481}
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-upgrade.XXXXXX")
baseline_directory="$work_directory/baseline"
environment_file="$work_directory/upgrade.env"
project_name="tekdocs_upgrade_$$"
test_email="upgrade-owner-$$@example.invalid"
test_password=$(openssl rand -base64 36 | tr -d '\n')
test_port=$((32000 + ($$ % 1000)))
mailpit_port=$((8200 + ($$ % 1000)))

baseline_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$baseline_directory/compose.yml" -f "$baseline_directory/compose.test.yml" "$@"
}

current_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" "$@"
}

cleanup() {
  current_compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

git -C "$repository_root" cat-file -e "$baseline_ref^{commit}"
mkdir -p "$baseline_directory"
git -C "$repository_root" archive "$baseline_ref" | tar -x -C "$baseline_directory"
"$baseline_directory/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
{
  echo "TEKDOCS_PORT=$test_port"
  echo "MAILPIT_UI_PORT=$mailpit_port"
} >> "$environment_file"

baseline_version=$(tr -d '[:space:]' < "$baseline_directory/VERSION")
current_version=$(tr -d '[:space:]' < "$repository_root/VERSION")
if [ "$baseline_version" != "0.0.10" ]; then
  echo "Upgrade rehearsal expected baseline 0.0.10, found $baseline_version" >&2
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
from apps.core.models import AuditEvent

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
print("Baseline identity fixture created")
'

baseline_compose down --remove-orphans

echo "Applying TekDocs $current_version to the preserved database"
current_compose up -d --build --wait backend
current_compose exec -T \
  -e UPGRADE_TEST_EMAIL="$test_email" \
  -e UPGRADE_TEST_PASSWORD="$test_password" \
  backend python manage.py shell -c '
import os
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from apps.accounts.mfa_storage import PREFIX, decrypt_mfa_value
from apps.accounts.models import TenantMembership, User
from apps.core.models import AuditEvent, InstallationState, Tenant

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
assert TenantMembership.objects.filter(tenant=state.tenant, user=owner).count() == 1
assert encrypted_secret.startswith(PREFIX)
assert decrypt_mfa_value(encrypted_secret)
assert AuditEvent.objects.filter(action="installation.owner_bootstrapped", actor=owner).count() == 1
assert AuditEvent.objects.filter(action="upgrade.fixture_created", actor=owner, metadata={}).count() == 1
print("Upgraded identity and authentication invariants verified")
'
current_compose exec -T backend python manage.py check
current_compose exec -T backend python manage.py makemigrations --check --dry-run

echo "Upgrade rehearsal passed: $baseline_version -> $current_version"
