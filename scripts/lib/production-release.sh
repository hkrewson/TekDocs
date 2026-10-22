#!/usr/bin/env bash

# Read reviewed release data as data, never as executable shell input.
tekdocs_load_release_receipt() {
  local root=$1 release=$2 key value count=0
  [[ "$release" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  local receipt="$root/scripts/releases/$release.images"
  [[ -f "$receipt" && ! -L "$receipt" ]] || return 1
  TEKDOCS_RELEASE_COMMIT= TEKDOCS_RELEASE_BACKEND= TEKDOCS_RELEASE_FRONTEND= TEKDOCS_RELEASE_RENDERER= TEKDOCS_RELEASE_MAILPIT=
  while IFS='=' read -r key value; do
    case "$key" in
      commit) [[ -z "$TEKDOCS_RELEASE_COMMIT" && "$value" =~ ^[0-9a-f]{40}$ ]] || return 1; TEKDOCS_RELEASE_COMMIT=$value ;;
      backend) [[ -z "$TEKDOCS_RELEASE_BACKEND" && "$value" =~ ^ghcr\.io/hkrewson/tekdocs-backend@sha256:[0-9a-f]{64}$ ]] || return 1; TEKDOCS_RELEASE_BACKEND=$value ;;
      frontend) [[ -z "$TEKDOCS_RELEASE_FRONTEND" && "$value" =~ ^ghcr\.io/hkrewson/tekdocs-frontend@sha256:[0-9a-f]{64}$ ]] || return 1; TEKDOCS_RELEASE_FRONTEND=$value ;;
      renderer) [[ -z "$TEKDOCS_RELEASE_RENDERER" && "$value" =~ ^ghcr\.io/hkrewson/tekdocs-diagram-renderer@sha256:[0-9a-f]{64}$ ]] || return 1; TEKDOCS_RELEASE_RENDERER=$value ;;
      mailpit) [[ -z "$TEKDOCS_RELEASE_MAILPIT" && "$value" =~ ^ghcr\.io/hkrewson/tekdocs-mailpit@sha256:[0-9a-f]{64}$ ]] || return 1; TEKDOCS_RELEASE_MAILPIT=$value ;;
      *) return 1 ;;
    esac
    count=$((count + 1))
  done < "$receipt"
  [[ -n "$TEKDOCS_RELEASE_COMMIT" && -n "$TEKDOCS_RELEASE_BACKEND" && -n "$TEKDOCS_RELEASE_FRONTEND" && -n "$TEKDOCS_RELEASE_RENDERER" ]] || return 1
  [[ "$count" -eq 4 || ( "$count" -eq 5 && -n "$TEKDOCS_RELEASE_MAILPIT" ) ]]
}

tekdocs_verify_release_images() {
  [[ "$TEKDOCS_RESOLVED_BACKEND_IMAGE" == "$TEKDOCS_RELEASE_BACKEND" &&
     "$TEKDOCS_RESOLVED_FRONTEND_IMAGE" == "$TEKDOCS_RELEASE_FRONTEND" &&
     "$TEKDOCS_RESOLVED_RENDERER_IMAGE" == "$TEKDOCS_RELEASE_RENDERER" &&
     "${TEKDOCS_RESOLVED_MAILPIT_IMAGE:-}" == "${TEKDOCS_RELEASE_MAILPIT:-}" ]]
}

# CI publishes this companion ref atomically with the application tag. Fetch into
# FETCH_HEAD only: do not modify the operator's branch, index, or working tree.
tekdocs_fetch_release_receipt() (
  local root=$1 release=$2 temporary receipt_commit parent
  [[ "$release" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  temporary=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-receipt.XXXXXX") || return 1
  trap 'rm -rf -- "$temporary"' EXIT
  git -C "$root" fetch origin "refs/tags/receipts/$release" >&2 || return 1
  receipt_commit=$(git -C "$root" rev-parse --verify 'FETCH_HEAD^{commit}') || return 1
  parent=$(git -C "$root" show -s --format=%P "$receipt_commit") || return 1
  [[ "$parent" =~ ^[0-9a-f]{40}$ ]] || return 1
  mkdir -p "$temporary/scripts/releases" || return 1
  git -C "$root" show "$receipt_commit:scripts/releases/$release.images" > "$temporary/scripts/releases/$release.images" || return 1
  tekdocs_load_release_receipt "$temporary" "$release" || return 1
  [[ "$TEKDOCS_RELEASE_COMMIT" == "$parent" && -n "$TEKDOCS_RELEASE_MAILPIT" ]] || return 1
  [[ "$(git -C "$root" diff-tree --no-commit-id --name-only -r "$receipt_commit")" == "scripts/releases/$release.images" ]] || return 1
  cat "$temporary/scripts/releases/$release.images"
)

# Keep historical checked-in receipts; obtain future receipts from CI when absent.
tekdocs_load_published_release() {
  local root=$1 release=$2 temporary status=0
  [[ "$release" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  if [[ -e "$root/scripts/releases/$release.images" || -L "$root/scripts/releases/$release.images" ]]; then
    tekdocs_load_release_receipt "$root" "$release"
    return $?
  fi
  temporary=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-load-receipt.XXXXXX") || return 1
  mkdir -p "$temporary/scripts/releases" || { rm -rf -- "$temporary"; return 1; }
  if tekdocs_fetch_release_receipt "$root" "$release" > "$temporary/scripts/releases/$release.images"; then
    tekdocs_load_release_receipt "$temporary" "$release" || status=1
  else
    status=1
  fi
  rm -rf -- "$temporary"
  return "$status"
}
