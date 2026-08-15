#!/usr/bin/env bash

TEKDOCS_BACKEND_REPOSITORY=ghcr.io/hkrewson/tekdocs-backend
TEKDOCS_FRONTEND_REPOSITORY=ghcr.io/hkrewson/tekdocs-frontend

tekdocs_resolve_digest_reference() {
  local repository=$1
  local tagged_reference=$2
  local digest_reference digest

  digest_reference=$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$tagged_reference" \
    | awk -v prefix="$repository@sha256:" 'index($0, prefix) == 1 {print; exit}')
  [[ "$digest_reference" == "$repository@sha256:"* ]] || {
    echo "The registry digest could not be resolved for $tagged_reference" >&2
    return 1
  }
  digest=${digest_reference#*@sha256:}
  [[ ${#digest} -eq 64 && "$digest" != *[!0-9a-f]* ]] || {
    echo "The registry returned an invalid digest for $tagged_reference" >&2
    return 1
  }
  printf '%s\n' "$digest_reference"
}

tekdocs_resolve_production_images() {
  local commit=$1
  local commit_tag backend_tagged_reference frontend_tagged_reference
  local backend_revision frontend_revision

  [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || {
    echo "A full 40-character Git commit is required to resolve production images." >&2
    return 1
  }
  commit_tag="sha-$commit"
  backend_tagged_reference="$TEKDOCS_BACKEND_REPOSITORY:$commit_tag"
  frontend_tagged_reference="$TEKDOCS_FRONTEND_REPOSITORY:$commit_tag"

  echo "Pulling validated production images for commit $commit"
  docker pull "$backend_tagged_reference"
  docker pull "$frontend_tagged_reference"

  backend_revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$backend_tagged_reference")
  frontend_revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$frontend_tagged_reference")
  [[ "$backend_revision" == "$commit" ]] || {
    echo "The backend image revision does not match the checked-out commit." >&2
    return 1
  }
  [[ "$frontend_revision" == "$commit" ]] || {
    echo "The frontend image revision does not match the checked-out commit." >&2
    return 1
  }

  TEKDOCS_RESOLVED_BACKEND_IMAGE=$(tekdocs_resolve_digest_reference "$TEKDOCS_BACKEND_REPOSITORY" "$backend_tagged_reference")
  TEKDOCS_RESOLVED_FRONTEND_IMAGE=$(tekdocs_resolve_digest_reference "$TEKDOCS_FRONTEND_REPOSITORY" "$frontend_tagged_reference")
  export TEKDOCS_RESOLVED_BACKEND_IMAGE TEKDOCS_RESOLVED_FRONTEND_IMAGE
}

tekdocs_persist_environment_value() {
  local environment_file=$1
  local name=$2
  local value=$3
  local environment_directory temporary

  environment_directory=$(dirname -- "$environment_file")
  temporary=$(mktemp "$environment_directory/.tekdocs-env.XXXXXX")
  awk -v name="$name" -v value="$value" '
    BEGIN { replaced = 0 }
    index($0, name "=") == 1 {
      if (!replaced) print name "=" value
      replaced = 1
      next
    }
    { print }
    END { if (!replaced) print name "=" value }
  ' "$environment_file" > "$temporary"
  chmod 0600 "$temporary"
  mv "$temporary" "$environment_file"
}
