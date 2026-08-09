#!/bin/sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root_dir"

for lock_file in backend/build-requirements.lock backend/requirements.lock backend/requirements-dev.lock; do
  test -s "$lock_file"
  grep -q -- '--hash=sha256:' "$lock_file"
done

unpinned_actions=$(rg -n 'uses:[[:space:]]+[^[:space:]]+@' .github/workflows \
  | grep -Ev '@[0-9a-f]{40}([[:space:]]|$)' || true)
if [ -n "$unpinned_actions" ]; then
  printf '%s\n' "$unpinned_actions"
  echo "GitHub Actions must use immutable 40-character commit SHAs." >&2
  exit 1
fi

if awk '/^[[:space:]]*image:/ && $0 !~ /@sha256:/{print FILENAME ":" FNR ":" $0; found=1} END{exit !found}' \
  compose.yml compose.test.yml compose.production-test.yml; then
  echo "Compose images must include an immutable sha256 digest." >&2
  exit 1
fi

if awk '/^FROM[[:space:]]+(python|node|nginx|mcr\.microsoft\.com)/ && $0 !~ /@sha256:/{print FILENAME ":" FNR ":" $0; found=1} END{exit !found}' \
  backend/Dockerfile frontend/Dockerfile frontend/Dockerfile.e2e; then
  echo "External Dockerfile bases must include an immutable sha256 digest." >&2
  exit 1
fi

echo "Supply-chain pin contract passed."
