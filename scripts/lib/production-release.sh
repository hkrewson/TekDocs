#!/usr/bin/env bash

# Read reviewed release data as data, never as executable shell input.
tekdocs_load_release_receipt() {
  local root=$1 release=$2 key value count=0
  [[ "$release" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  local receipt="$root/scripts/releases/$release.images"
  [[ -f "$receipt" && ! -L "$receipt" ]] || return 1
  TEKDOCS_RELEASE_COMMIT= TEKDOCS_RELEASE_BACKEND= TEKDOCS_RELEASE_FRONTEND= TEKDOCS_RELEASE_RENDERER=
  while IFS='=' read -r key value; do
    case "$key" in
      commit) [[ -z "$TEKDOCS_RELEASE_COMMIT" && "$value" =~ ^[0-9a-f]{40}$ ]] || return 1; TEKDOCS_RELEASE_COMMIT=$value ;;
      backend) [[ -z "$TEKDOCS_RELEASE_BACKEND" && "$value" =~ ^ghcr\.io/hkrewson/tekdocs-backend@sha256:[0-9a-f]{64}$ ]] || return 1; TEKDOCS_RELEASE_BACKEND=$value ;;
      frontend) [[ -z "$TEKDOCS_RELEASE_FRONTEND" && "$value" =~ ^ghcr\.io/hkrewson/tekdocs-frontend@sha256:[0-9a-f]{64}$ ]] || return 1; TEKDOCS_RELEASE_FRONTEND=$value ;;
      renderer) [[ -z "$TEKDOCS_RELEASE_RENDERER" && "$value" =~ ^ghcr\.io/hkrewson/tekdocs-diagram-renderer@sha256:[0-9a-f]{64}$ ]] || return 1; TEKDOCS_RELEASE_RENDERER=$value ;;
      *) return 1 ;;
    esac
    count=$((count + 1))
  done < "$receipt"
  [[ "$count" -eq 4 ]]
}

tekdocs_verify_release_images() {
  [[ "$TEKDOCS_RESOLVED_BACKEND_IMAGE" == "$TEKDOCS_RELEASE_BACKEND" &&
     "$TEKDOCS_RESOLVED_FRONTEND_IMAGE" == "$TEKDOCS_RELEASE_FRONTEND" &&
     "$TEKDOCS_RESOLVED_RENDERER_IMAGE" == "$TEKDOCS_RELEASE_RENDERER" ]]
}
