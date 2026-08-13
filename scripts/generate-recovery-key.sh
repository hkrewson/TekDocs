#!/bin/sh
set -eu

target=${1:-tekdocs-recovery.key}
if [ -e "$target" ]; then
  echo "Refusing to overwrite an existing recovery key." >&2
  exit 1
fi
umask 077
openssl rand -base64 32 | tr '+/' '-_' > "$target"
chmod 0600 "$target"
echo "Created a separate-custody recovery key at $target"
