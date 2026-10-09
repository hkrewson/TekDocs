#!/bin/sh

# Print one lowercase SHA-256 digest, or fail before a recovery set is published.
recovery_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    checksum_output=$(sha256sum "$1") || return 1
  elif command -v shasum >/dev/null 2>&1; then
    checksum_output=$(shasum -a 256 "$1") || return 1
  else
    echo "A SHA-256 checksum utility is required for recovery." >&2
    return 1
  fi
  checksum_digest=${checksum_output%% *}
  case "$checksum_digest" in
    *[!0-9a-f]*) echo "Recovery artifact checksum is invalid." >&2; return 1 ;;
  esac
  if [ "${#checksum_digest}" -ne 64 ]; then
    echo "Recovery artifact checksum is invalid." >&2
    return 1
  fi
  printf '%s\n' "$checksum_digest"
}
