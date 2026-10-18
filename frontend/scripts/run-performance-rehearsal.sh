#!/bin/sh
set -u

: "${PLAYWRIGHT_SAFE_SUMMARY:?Safe summary destination is required}"
: "${TEKDOCS_PERFORMANCE_DIAGNOSTICS:?Diagnostic destination is required}"
status=0
npx playwright test --config=playwright.compose.config.ts --project=chromium \
  --workers=1 --repeat-each="${TEKDOCS_PERFORMANCE_REPETITIONS:-1}" \
  e2e/performance.spec.ts || status=$?

# Docker writes as root on Linux. Export only the value-safe JSON reports for
# the host uploader, on failure too; raw Playwright output stays container-local.
for report in "$PLAYWRIGHT_SAFE_SUMMARY" "$TEKDOCS_PERFORMANCE_DIAGNOSTICS"/*.json; do
  [ -f "$report" ] || continue
  chmod 0644 "$report" || exit 1
done
exit "$status"
