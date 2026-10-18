#!/bin/sh
set -eu
repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
docker run --rm --entrypoint sh \
  -v "$repository_root/frontend/scripts/run-performance-rehearsal.sh:/run-performance.sh:ro" \
  nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de -c '
    set -eu
    mkdir -p /tmp/fake-bin /tmp/reports/diagnostics
    cat > /tmp/fake-bin/npx <<"STUB"
#!/bin/sh
printf "{\"schema_version\": 1}\n" > "$PLAYWRIGHT_SAFE_SUMMARY"
printf "{\"schema_version\": 1}\n" > "$TEKDOCS_PERFORMANCE_DIAGNOSTICS/legacy-390-0.json"
chmod 0600 "$PLAYWRIGHT_SAFE_SUMMARY" "$TEKDOCS_PERFORMANCE_DIAGNOSTICS/legacy-390-0.json"
exit "$FAKE_TEST_EXIT"
STUB
    chmod 0755 /tmp/fake-bin/npx
    export PATH=/tmp/fake-bin:$PATH
    export PLAYWRIGHT_SAFE_SUMMARY=/tmp/reports/summary.json
    export TEKDOCS_PERFORMANCE_DIAGNOSTICS=/tmp/reports/diagnostics
    for expected in 0 7; do
      export FAKE_TEST_EXIT=$expected
      actual=0
      sh /run-performance.sh || actual=$?
      test "$actual" -eq "$expected"
      su nobody -s /bin/sh -c "cat /tmp/reports/summary.json /tmp/reports/diagnostics/legacy-390-0.json" >/dev/null
    done
  '
echo "Performance reports readable by non-root uploader; success/failure exit codes preserved."
