#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mode=${1:-check}

run_gate() {
  case "$mode" in
    check)
      npm --prefix "$repository_root/frontend" run lint
      npm --prefix "$repository_root/frontend" run typecheck
      npm --prefix "$repository_root/frontend" run test
      npm --prefix "$repository_root/frontend" run build
      ;;
    test) npm --prefix "$repository_root/frontend" run test ;;
    audit) npm --prefix "$repository_root/frontend" audit --omit=dev --audit-level=high ;;
    *) echo "Unknown frontend gate: $mode" >&2; exit 2 ;;
  esac
}

node_major=""
if command -v node >/dev/null 2>&1; then
  node_major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || true)
fi
if [ "$node_major" = "24" ] && command -v npm >/dev/null 2>&1; then
  run_gate
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Frontend gates require Node 24 with npm, or Docker for the isolated Node 24 fallback." >&2
  exit 1
fi

echo "Host Node ${node_major:-unavailable} is unsupported; running the frontend $mode gate in isolated Node 24."
docker run --rm \
  -e FRONTEND_GATE_MODE="$mode" \
  -v "$repository_root/frontend:/src:ro" \
  -w /work \
  node:24-alpine sh -ec '
    tar -C /src --exclude=node_modules --exclude=dist --exclude=coverage --exclude=playwright-report --exclude=test-results -cf - . | tar -C /work -xf -
    npm ci --no-audit --no-fund
    case "$FRONTEND_GATE_MODE" in
      check) npm run lint && npm run typecheck && npm run test && npm run build ;;
      test) npm run test ;;
      audit) npm audit --omit=dev --audit-level=high ;;
      *) exit 2 ;;
    esac
  '
