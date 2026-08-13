#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-browser-artifacts.XXXXXX")
trap 'rm -rf "$work_directory"' EXIT HUP INT TERM

safe="$work_directory/safe.json"
unsafe="$work_directory/unsafe.json"
linked="$work_directory/linked.json"

printf '%s\n' '{"schema_version": 1, "status": "passed", "projects": []}' > "$safe"
"$repository_root/scripts/check-browser-artifacts.sh" "$safe" >/dev/null

printf '%s\n' '{"schema_version": 1, "status": "failed", "password": "must-not-escape"}' > "$unsafe"
if "$repository_root/scripts/check-browser-artifacts.sh" "$unsafe" >/dev/null 2>&1; then
  echo "Secret-bearing browser artifact was accepted." >&2
  exit 1
fi

ln -s "$safe" "$linked"
if "$repository_root/scripts/check-browser-artifacts.sh" "$linked" >/dev/null 2>&1; then
  echo "Symbolic-link browser artifact was accepted." >&2
  exit 1
fi

echo "Browser artifact hygiene rejection tests passed."
