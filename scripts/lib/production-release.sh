#!/usr/bin/env bash

tekdocs_release_is_newer() {
  local left=$1 right=$2
  [[ "$left" =~ ^v([0-9]{1,9})\.([0-9]{1,9})\.([0-9]{1,9})$ ]] || return 2
  local left_major=${BASH_REMATCH[1]} left_minor=${BASH_REMATCH[2]} left_patch=${BASH_REMATCH[3]}
  [[ "$right" =~ ^v([0-9]{1,9})\.([0-9]{1,9})\.([0-9]{1,9})$ ]] || return 2
  local right_major=${BASH_REMATCH[1]} right_minor=${BASH_REMATCH[2]} right_patch=${BASH_REMATCH[3]}
  ((10#$left_major > 10#$right_major)) && return 0
  ((10#$left_major < 10#$right_major)) && return 1
  ((10#$left_minor > 10#$right_minor)) && return 0
  ((10#$left_minor < 10#$right_minor)) && return 1
  ((10#$left_patch > 10#$right_patch))
}

# Print stable releases that have both an application tag and companion receipt
# tag. The application commit is peeled when a future annotated tag is used.
tekdocs_discover_published_releases() {
  local root=$1 references sha ref release existing index insert_at candidate commit fallback
  local application_releases=() receipt_releases=() published_releases=() sorted_releases=()
  references=$(git -C "$root" ls-remote --tags origin 'refs/tags/v*' 'refs/tags/receipts/v*') || return 1
  while IFS=$'\t' read -r sha ref; do
    [[ -n "$sha" && -n "$ref" ]] || continue
    case "$ref" in
      refs/tags/v*'^{}') continue ;;
      refs/tags/v*) release=${ref#refs/tags/} ;;
      refs/tags/receipts/v*) release=${ref#refs/tags/receipts/} ;;
      *) continue ;;
    esac
    [[ "$release" =~ ^v[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}$ ]] || continue
    if [[ "$ref" == refs/tags/receipts/* ]]; then
      receipt_releases+=("$release")
    else
      application_releases+=("$release")
    fi
  done <<< "$references"
  for release in "${application_releases[@]}"; do
    for existing in "${receipt_releases[@]}"; do
      if [[ "$release" == "$existing" ]]; then
        published_releases+=("$release")
        break
      fi
    done
  done
  for release in "${published_releases[@]}"; do
    insert_at=${#sorted_releases[@]}
    for index in "${!sorted_releases[@]}"; do
      if tekdocs_release_is_newer "$release" "${sorted_releases[$index]}"; then
        insert_at=$index
        break
      fi
    done
    sorted_releases=("${sorted_releases[@]:0:$insert_at}" "$release" "${sorted_releases[@]:$insert_at}")
  done
  ((${#sorted_releases[@]} > 0)) || return 1
  for candidate in "${sorted_releases[@]}"; do
    commit=
    fallback=
    while IFS=$'\t' read -r sha ref; do
      case "$ref" in
        "refs/tags/$candidate^{}") commit=$sha; break ;;
        "refs/tags/$candidate") fallback=$sha ;;
      esac
    done <<< "$references"
    [[ -n "$commit" ]] || commit=$fallback
    [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || return 1
    printf '%s\t%s\n' "$candidate" "$commit"
  done
}

tekdocs_latest_published_release() {
  local root=$1 catalog first
  catalog=$(tekdocs_discover_published_releases "$root") || return 1
  first=${catalog%%$'\n'*}
  printf '%s\n' "${first%%$'\t'*}"
}

# Use the CI-created receipt commit time as the publication clock for unattended
# soak windows. This is scheduling metadata only; receipt contents and ancestry
# are validated independently before any deployment activity.
tekdocs_release_receipt_epoch() {
  local root=$1 release=$2 receipt receipt_commit parent changed_path published_at expected
  [[ "$release" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  git -C "$root" fetch --quiet origin "refs/tags/receipts/$release" || return 1
  receipt_commit=$(git -C "$root" rev-parse --verify 'FETCH_HEAD^{commit}') || return 1
  parent=$(git -C "$root" show -s --format=%P "$receipt_commit") || return 1
  [[ "$parent" == "$TEKDOCS_RELEASE_COMMIT" ]] || return 1
  changed_path=$(git -C "$root" diff-tree --no-commit-id --name-only -r "$receipt_commit") || return 1
  [[ "$changed_path" == "scripts/releases/$release.images" ]] || return 1
  receipt=$(git -C "$root" show "$receipt_commit:scripts/releases/$release.images") || return 1
  expected=$(printf 'commit=%s\nbackend=%s\nfrontend=%s\nrenderer=%s' \
    "$TEKDOCS_RELEASE_COMMIT" "$TEKDOCS_RELEASE_BACKEND" \
    "$TEKDOCS_RELEASE_FRONTEND" "$TEKDOCS_RELEASE_RENDERER")
  if [[ -n "$TEKDOCS_RELEASE_MAILPIT" ]]; then
    expected+=$(printf '\nmailpit=%s' "$TEKDOCS_RELEASE_MAILPIT")
  fi
  [[ "$receipt" == "$expected" ]] || return 1
  published_at=$(git -C "$root" show -s --format=%ct "$receipt_commit") || return 1
  [[ "$published_at" =~ ^[0-9]{1,12}$ ]] || return 1
  printf '%s\n' "$published_at"
}

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
