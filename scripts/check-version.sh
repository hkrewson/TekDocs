#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
release_version=$(tr -d '[:space:]' < "$repository_root/VERSION")
backend_version=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$repository_root/backend/pyproject.toml" | head -n 1)
frontend_version=$(sed -n 's/^[[:space:]]*"version": "\([^"]*\)",/\1/p' "$repository_root/frontend/package.json" | head -n 1)
frontend_lock_version=$(sed -n 's/^[[:space:]]*"version": "\([^"]*\)",/\1/p' "$repository_root/frontend/package-lock.json" | head -n 1)

for version_value in "$backend_version" "$frontend_version" "$frontend_lock_version"; do
  if [ "$version_value" != "$release_version" ]; then
    echo "Version metadata does not agree with VERSION=$release_version" >&2
    exit 1
  fi
done

echo "Version metadata agrees at $release_version"
