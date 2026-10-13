#!/bin/sh

recovery_secret_tar() {
  # BSD tar otherwise adds AppleDouble files for macOS extended attributes.
  # These are not deployment keys and must never enter the allowlisted archive.
  COPYFILE_DISABLE=1 tar -cf - -C "$@"
}

recovery_assert_no_plaintext() {
  recovery_scan_pattern=$1
  shift
  recovery_scan_status=0
  grep -aFq -e "$recovery_scan_pattern" "$@" 2>/dev/null || recovery_scan_status=$?
  case "$recovery_scan_status" in
    1) return 0 ;;
    0) echo "An encrypted recovery artifact disclosed a deployment secret." >&2; return 1 ;;
    *) echo "Recovery artifact plaintext scan could not complete." >&2; return 2 ;;
  esac
}
