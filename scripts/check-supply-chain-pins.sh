#!/bin/sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root_dir"

python3 scripts/check_renderer_dependency_contract.py
grep -q 'python3 scripts/check_renderer_dependency_contract.py' .github/workflows/build.yml
grep -q 'path: artifacts/renderer-dependency-contract.json' .github/workflows/build.yml
grep -q 'category supply_chain' .github/workflows/build.yml
grep -q 'category upgrade_and_restore' .github/workflows/extended-validation.yml
grep -q 'assemble-diagram-release-evidence:' Makefile

for lock_file in backend/build-requirements.lock backend/requirements.lock backend/requirements-dev.lock; do
  test -s "$lock_file"
  grep -q -- '--hash=sha256:' "$lock_file"
done

grep -q 'zaproxy/zap-stable@sha256:[0-9a-f]\{64\}' tests/rehearsals/rehearse-production-image.sh
grep -q 'permission_image=postgres:17-alpine@sha256:[0-9a-f]\{64\}' scripts/setup-production.sh

mailpit_references=$(grep -Eho 'axllent/mailpit:edge@sha256:[0-9a-f]{64}' \
  compose.yml Makefile .github/workflows/build.yml)
mailpit_reference_count=$(printf '%s\n' "$mailpit_references" | wc -l | tr -d ' ')
mailpit_digest_count=$(printf '%s\n' "$mailpit_references" | sort -u | wc -l | tr -d ' ')
if [ "$mailpit_reference_count" -ne 3 ] || [ "$mailpit_digest_count" -ne 1 ]; then
  echo "Compose, CI, and the local security gate must share one immutable Mailpit digest." >&2
  exit 1
fi

unpinned_actions=$(grep -REn 'uses:[[:space:]]+[^[:space:]]+@' .github/workflows \
  | grep -Ev '@[0-9a-f]{40}([[:space:]]|$)' || true)
if [ -n "$unpinned_actions" ]; then
  printf '%s\n' "$unpinned_actions"
  echo "GitHub Actions must use immutable 40-character commit SHAs." >&2
  exit 1
fi

if awk '/^[[:space:]]*image:/ && $0 !~ /@sha256:/ && $0 !~ /\$\{TEKDOCS_(BACKEND|FRONTEND|RENDERER)_IMAGE:/{print FILENAME ":" FNR ":" $0; found=1} END{exit !found}' \
  compose.yml compose.test.yml compose.production.yml compose.secret-files.yml compose.smtp-secret.yml compose.traefik.yml \
  compose.oidc-secret.yml compose.bootstrap-secret.yml compose.images.yml; then
  echo "Compose images must include an immutable sha256 digest." >&2
  exit 1
fi

if awk '/^FROM[[:space:]]+(python|node|nginx|mcr\.microsoft\.com)/ && $0 !~ /@sha256:/{print FILENAME ":" FNR ":" $0; found=1} END{exit !found}' \
  backend/Dockerfile frontend/Dockerfile frontend/Dockerfile.e2e renderer/Dockerfile; then
  echo "External Dockerfile bases must include an immutable sha256 digest." >&2
  exit 1
fi

echo "Supply-chain pin contract passed."
