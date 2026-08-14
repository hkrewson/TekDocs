#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-production-image.XXXXXX")
environment_file="$work_directory/production-image.env"
secret_directory="$work_directory/secrets"
project_name="tekdocs_production_image_$$"
run_dast=${TEKDOCS_RUN_DAST:-false}

production_compose() {
  docker compose --project-name "$project_name" --env-file "$environment_file" \
    -f "$repository_root/compose.yml" -f "$repository_root/compose.test.yml" \
    -f "$repository_root/compose.production.yml" -f "$repository_root/compose.secret-files.yml" \
    -f "$repository_root/compose.smtp-secret.yml" -f "$repository_root/compose.oidc-secret.yml" \
    -f "$repository_root/compose.bootstrap-secret.yml" "$@"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "Production-target rehearsal failed; recent service logs follow." >&2
    production_compose logs --no-color --tail=120 backend frontend >&2 || true
  fi
  production_compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1 || true
  rm -rf "$work_directory"
}
trap cleanup EXIT HUP INT TERM

"$repository_root/scripts/bootstrap-env.sh" "$environment_file" >/dev/null
mkdir -m 0700 "$secret_directory"

copy_environment_secret() {
  name="$1"
  target="$2"
  value=$(sed -n "s/^${name}=//p" "$environment_file" | head -n 1)
  if [ -z "$value" ]; then
    echo "Production rehearsal could not prepare $name" >&2
    exit 1
  fi
  printf '%s\n' "$value" > "$secret_directory/$target"
  chmod 0600 "$secret_directory/$target"
}

copy_environment_secret DJANGO_SECRET_KEY django_secret_key
copy_environment_secret POSTGRES_OWNER_PASSWORD postgres_owner_password
copy_environment_secret POSTGRES_RUNTIME_PASSWORD postgres_runtime_password
copy_environment_secret TEKDOCS_MASTER_KEY tekdocs_master_key
copy_environment_secret TEKDOCS_PUBLICATION_SIGNING_KEY publication_signing_key
copy_environment_secret TEKDOCS_BOOTSTRAP_TOKEN bootstrap_token
sanitized_environment_file="$work_directory/production-image-sanitized.env"
sed -E \
  -e 's/^(DJANGO_SECRET_KEY|POSTGRES_OWNER_PASSWORD|POSTGRES_RUNTIME_PASSWORD|TEKDOCS_MASTER_KEY|TEKDOCS_PUBLICATION_SIGNING_KEY|TEKDOCS_BOOTSTRAP_TOKEN)=.*/\1=/' \
  "$environment_file" > "$sanitized_environment_file"
chmod 0600 "$sanitized_environment_file"
mv "$sanitized_environment_file" "$environment_file"
email_secret=$(openssl rand -hex 32)
oidc_secret=$(openssl rand -hex 32)
printf '%s\n' "$email_secret" > "$secret_directory/email_host_password"
printf '%s\n' "$oidc_secret" > "$secret_directory/oidc_client_secret"
chmod 0600 "$secret_directory/email_host_password" "$secret_directory/oidc_client_secret"
{
  echo "TEKDOCS_PORT=0"
  echo "MAILPIT_UI_PORT=0"
  echo "TEKDOCS_SECRET_DIRECTORY=$secret_directory"
  echo "EMAIL_HOST_USER=production-rehearsal"
  echo "TEKDOCS_OIDC_PROVIDER_ID=rehearsal-sso"
  echo "TEKDOCS_OIDC_PROVIDER_NAME=Rehearsal SSO"
  echo "TEKDOCS_OIDC_DISCOVERY_URL=https://identity.example.invalid/.well-known/openid-configuration"
  echo "TEKDOCS_OIDC_CLIENT_ID=tekdocs-rehearsal"
  echo "TEKDOCS_CLAMAV_HOST=clamav"
} >> "$environment_file"

echo "Starting isolated production-target image rehearsal"
production_compose up -d --build --wait
production_compose exec -T frontend wget -q -O - http://127.0.0.1:8080/api/v1/health/ready | grep -q '"status":"ok"'
production_compose exec -T backend python manage.py migrate --check
production_compose exec -T backend python -c 'import importlib.util; assert importlib.util.find_spec("pytest") is None'
production_compose exec -T backend python -c 'import os; from django.conf import settings; assert os.environ["TEKDOCS_IMAGE_VARIANT"] == "production"; assert settings.TEKDOCS_ATTACHMENT_SCANNER == "apps.core.attachment_security.ClamAVAttachmentScanner"; assert settings.TEKDOCS_CLAMAV_HOST'
production_compose exec -T backend python -c 'from apps.core.attachment_security import attachment_scanner; assert attachment_scanner().scan(filename="probe.txt", media_type="text/plain", content=b"TekDocs production scanner probe").engine == "clamav/instream"'
backend_id=$(production_compose ps -q backend)
backend_user=$(docker inspect --format '{{.Config.User}}' "$backend_id")
if [ "$backend_user" != "tekdocs" ] && [ "$backend_user" != "10001" ]; then
  echo "Production backend image must run as the unprivileged TekDocs user" >&2
  exit 1
fi

echo "Verifying production container isolation controls"
for service in migrate backend worker scheduler; do
  container_id=$(production_compose ps -q --all "$service")
  [ "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$container_id")" = "true" ]
  docker inspect --format '{{json .HostConfig.CapDrop}}' "$container_id" | grep -q '"ALL"'
  docker inspect --format '{{json .HostConfig.SecurityOpt}}' "$container_id" | grep -q 'no-new-privileges:true'
  pids_limit=$(docker inspect --format '{{.HostConfig.PidsLimit}}' "$container_id")
  [ "$pids_limit" -gt 0 ]
done
frontend_id=$(production_compose ps -q frontend)
[ "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$frontend_id")" = "true" ]
docker inspect --format '{{json .HostConfig.SecurityOpt}}' "$frontend_id" | grep -q 'no-new-privileges:true'

echo "Verifying production secrets remain file-backed and value-free"
for service in db migrate backend worker scheduler; do
  container_id=$(production_compose ps -q --all "$service")
  environment_output=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container_id")
  image_id=$(docker inspect --format '{{.Image}}' "$container_id")
  image_history=$(docker history --no-trunc "$image_id")
  for secret_file in "$secret_directory"/*; do
    secret_value=$(sed -n '1p' "$secret_file")
    if printf '%s' "$environment_output" | grep -Fq "$secret_value"; then
      echo "Production $service container environment contains a secret value" >&2
      exit 1
    fi
    if printf '%s' "$image_history" | grep -Fq "$secret_value"; then
      echo "Production $service image history contains a secret value" >&2
      exit 1
    fi
  done
done
for secret_file in "$secret_directory"/*; do
  secret_value=$(sed -n '1p' "$secret_file")
  if grep -Fq "$secret_value" "$environment_file"; then
    echo "Production environment file contains a secret value" >&2
    exit 1
  fi
done
production_compose exec -T backend sh -c 'test -r /run/secrets/django_secret_key && test ! -e /run/secrets/postgres_owner_password'
production_compose run --rm --no-deps migrate sh -c 'test -r /run/secrets/postgres_owner_password && test ! -e /run/secrets/email_host_password'
production_compose exec -T db sh -c 'test -r /run/secrets/postgres_owner_password && test ! -e /run/secrets/django_secret_key'

combined_logs=$(production_compose logs --no-color)
for secret_file in "$secret_directory"/*; do
  secret_value=$(sed -n '1p' "$secret_file")
  if printf '%s' "$combined_logs" | grep -Fq "$secret_value"; then
    echo "Production service logs contain a secret value" >&2
    exit 1
  fi
done
if printf '%s' "$combined_logs" | grep -Fq "$secret_directory"; then
  echo "Production service logs contain the host secret directory" >&2
  exit 1
fi
request_log=$(production_compose logs --no-color backend | sed -n 's/^[^|]*| //p' | grep '"event":"request_complete"' | tail -n 1)
[ -n "$request_log" ] || { echo "Production request did not emit a structured event" >&2; exit 1; }
printf '%s' "$request_log" | python3 -c 'import json,sys; value=json.load(sys.stdin); required={"timestamp","level","logger","event","request_id","method","route","status_code","duration_ms"}; assert required <= value.keys(); assert value["event"] == "request_complete"'

failure_log="$work_directory/ambiguous-secret.log"
if production_compose run --rm --no-deps -e DJANGO_SECRET_KEY=ambiguous-direct-value \
  backend python manage.py check > "$failure_log" 2>&1; then
  echo "Production startup accepted ambiguous direct and file secret sources" >&2
  exit 1
fi
grep -q 'set either DJANGO_SECRET_KEY or DJANGO_SECRET_KEY_FILE, not both' "$failure_log"
if grep -Fq 'ambiguous-direct-value' "$failure_log" || grep -Fq "$secret_directory" "$failure_log"; then
  echo "Secret-source validation disclosed a value or host path" >&2
  exit 1
fi
if [ "$run_dast" = "true" ]; then
  echo "Running the pinned unauthenticated DAST baseline"
  docker run --rm --network "container:$frontend_id" \
    --tmpfs /zap/wrk:rw,noexec,nosuid,size=16m \
    -v "$repository_root/.zap:/zap/rules:ro" \
    zaproxy/zap-stable@sha256:781a2bdaea47324e7bab583e2263f21d257b0aee61ed51521a5be45f5f5081ef \
    zap-baseline.py -t http://localhost:8080 -m 1 -I -c /zap/rules/rules.tsv
fi
echo "Production-target image rehearsal passed"
