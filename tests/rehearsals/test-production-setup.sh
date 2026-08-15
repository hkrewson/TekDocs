#!/usr/bin/env bash
set -Eeuo pipefail

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-setup-contract.XXXXXX")
fake_bin="$work_directory/bin"
environment_file="$work_directory/production.env"
secret_directory="$work_directory/secrets"
commit=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

cleanup() {
  rm -rf "$work_directory"
}
trap cleanup EXIT

mkdir -p "$fake_bin"

cat > "$fake_bin/git" <<'EOF'
#!/bin/sh
case " $* " in
  *" status --porcelain "*) exit 0 ;;
  *" rev-parse HEAD "*) printf '%s\n' "$TEKDOCS_TEST_COMMIT" ;;
  *) echo "unexpected git invocation: $*" >&2; exit 1 ;;
esac
EOF

cat > "$fake_bin/curl" <<'EOF'
#!/bin/sh
case " $* " in
  *"/api/v1/bootstrap/status"*) printf '%s\n' '{"bootstrap_required":false}' ;;
esac
exit 0
EOF

cat > "$fake_bin/docker" <<'EOF'
#!/bin/sh
case " $* " in
  *" compose version "*) exit 0 ;;
  *" network inspect "*) exit 0 ;;
  *" image inspect "*)
    case "$*" in
      *org.opencontainers.image.revision*) printf '%s\n' "$TEKDOCS_TEST_COMMIT" ;;
      *tekdocs-backend*) printf '%s@sha256:%064d\n' 'ghcr.io/hkrewson/tekdocs-backend' 0 ;;
      *tekdocs-frontend*) printf '%s@sha256:%064d\n' 'ghcr.io/hkrewson/tekdocs-frontend' 1 ;;
      *) echo "unexpected image inspection: $*" >&2; exit 1 ;;
    esac
    ;;
  *" compose "*" exec -T backend cat /run/secrets/bootstrap_token "*)
    printf '%s\n' 'contract-test-deployment-token'
    ;;
  *" rm -f /secrets/bootstrap_token "*)
    rm -f "$TEKDOCS_TEST_SECRET_DIRECTORY/bootstrap_token"
    ;;
  *" compose "*) exit 0 ;;
  *" pull "*) exit 0 ;;
  *" run "*) exit 0 ;;
  *) echo "unexpected docker invocation: $*" >&2; exit 1 ;;
esac
EOF

chmod 0755 "$fake_bin/git" "$fake_bin/curl" "$fake_bin/docker"

output=$(PATH="$fake_bin:$PATH" TEKDOCS_TEST_COMMIT="$commit" \
  TEKDOCS_TEST_SECRET_DIRECTORY="$secret_directory" \
  "$repository_root/scripts/setup-production.sh" \
    --domain docs.example.com \
    --secret-directory "$secret_directory" \
    --timezone America/Chicago \
    --proxy-network edge \
    --traefik-entrypoint web \
    --env-file "$environment_file")
canonical_secret_directory=$(CDPATH= cd -- "$secret_directory" && pwd -P)

grep -q '^TEKDOCS_DOMAIN=docs.example.com$' "$environment_file"
grep -q '^TEKDOCS_PROXY_NETWORK=edge$' "$environment_file"
grep -q '^TEKDOCS_TRAEFIK_ENTRYPOINT=web$' "$environment_file"
grep -q '^TEKDOCS_SECRET_DIRECTORY='"$canonical_secret_directory"'$' "$environment_file"
grep -q '^DJANGO_ALLOWED_HOSTS=docs.example.com,localhost,127.0.0.1,backend,tekdocs-backend,frontend$' "$environment_file"
grep -q '^DJANGO_CSRF_TRUSTED_ORIGINS=https://docs.example.com$' "$environment_file"
grep -q '^TEKDOCS_PUBLIC_URL=https://docs.example.com$' "$environment_file"
grep -q '^TEKDOCS_ALLOW_DEVELOPMENT_IMAGE=false$' "$environment_file"
grep -q '^SECURE_SSL_REDIRECT=true$' "$environment_file"
grep -q '^TZ=America/Chicago$' "$environment_file"
grep -q '^TEKDOCS_BACKEND_IMAGE=ghcr.io/hkrewson/tekdocs-backend@sha256:' "$environment_file"
grep -q '^TEKDOCS_FRONTEND_IMAGE=ghcr.io/hkrewson/tekdocs-frontend@sha256:' "$environment_file"

for secret_name in \
  django_secret_key \
  postgres_owner_password \
  postgres_runtime_password \
  tekdocs_master_key \
  publication_signing_key \
  bootstrap_token; do
  test -s "$secret_directory/$secret_name"
done

grep -q 'Deployment token:' <<< "$output"
grep -q 'contract-test-deployment-token' <<< "$output"
grep -q 'setup-production.sh --finalize' <<< "$output"

finalize_output=$(PATH="$fake_bin:$PATH" TEKDOCS_TEST_COMMIT="$commit" \
  TEKDOCS_TEST_SECRET_DIRECTORY="$secret_directory" \
  "$repository_root/scripts/setup-production.sh" \
    --finalize \
    --env-file "$environment_file")
test ! -e "$secret_directory/bootstrap_token"
grep -q 'bootstrap secret has been removed' <<< "$finalize_output"

echo "Production setup contract passed."
