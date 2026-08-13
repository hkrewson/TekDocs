#!/bin/sh
set -eu

artifact=${1:-}
[ -n "$artifact" ] && [ -f "$artifact" ] || { echo "A browser summary artifact is required." >&2; exit 1; }
[ ! -L "$artifact" ] || { echo "Browser artifacts may not be symbolic links." >&2; exit 1; }

case "$artifact" in
  *.json) ;;
  *) echo "Only the value-free JSON browser summary may be retained." >&2; exit 1 ;;
esac

size=$(wc -c < "$artifact" | tr -d ' ')
[ "$size" -le 1048576 ] || { echo "Browser summary exceeds the one MiB retention ceiling." >&2; exit 1; }

if grep -Eiq 'otpauth:|BEGIN [A-Z ]*PRIVATE KEY|password[" ]*[:=]|recovery.?code[" ]*[:=]|authorization[" ]*[:=]|cookie[" ]*[:=]|csrfmiddlewaretoken|tekdocs_[a-z0-9_-]*secret' "$artifact"; then
  echo "Browser summary contains prohibited secret-bearing material." >&2
  exit 1
fi

grep -q '"schema_version": 1' "$artifact" || { echo "Browser summary schema is invalid." >&2; exit 1; }
grep -Eq '"status": "(passed|failed|timedout|interrupted)"' "$artifact" || { echo "Browser summary status is invalid." >&2; exit 1; }
echo "Browser artifact hygiene passed."
