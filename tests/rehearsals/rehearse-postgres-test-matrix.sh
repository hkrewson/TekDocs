#!/bin/sh

#==================# PostgreSQL Test Matrix #==================#
#
# Run the same isolated PostgreSQL coverage boundaries used by CI, with the large
# core selection divided into three local partitions, then merge and enforce
# coverage. Isolation preserves tests that modify cluster roles or schema;
# bounded batches keep local Docker memory predictable.
#
# Docker CPUs | Docker memory | Concurrent shards
# 10 or more  | 7 GB or more  | all ten
# otherwise   | any           | two batches of five
#
#=========================# VARIABLES #=========================#

set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
shard_runner="$repository_root/tests/rehearsals/rehearse-postgres-test-shard.sh"
coverage_merger="$repository_root/scripts/combine-postgres-coverage.sh"
work_directory=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-postgres-matrix.XXXXXX")
combined_directory="$work_directory/coverage"
active_pids=""
parallel_shards=${TEKDOCS_POSTGRES_MATRIX_PARALLEL_SHARDS:-auto}

#=========================# FUNCTIONS #=========================#

cleanup() {
  status=$?
  trap - EXIT HUP INT TERM
  for pid in $active_pids; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  for pid in $active_pids; do
    wait "$pid" >/dev/null 2>&1 || true
  done
  rm -rf "$work_directory"
  exit "$status"
}

run_shard() {
  shard=$1
  "$shard_runner" "$shard" >"$work_directory/$shard.log" 2>&1
}

run_batch() {
  batch_shards=$*
  active_pids=""

  for shard in $batch_shards; do
    run_shard "$shard" &
    pid=$!
    active_pids="$active_pids $pid"
    echo "$pid" >"$work_directory/$shard.pid"
  done

  batch_failed=0
  for shard in $batch_shards; do
    pid=$(cat "$work_directory/$shard.pid")
    if wait "$pid"; then
      tail -n 1 "$work_directory/$shard.log"
    else
      echo "PostgreSQL test shard failed: $shard" >&2
      cat "$work_directory/$shard.log" >&2
      batch_failed=1
    fi
  done
  active_pids=""

  test "$batch_failed" -eq 0
}

stage_coverage() {
  mkdir -p "$combined_directory"
  for shard in route-access route-methods route-session accounts core-a core-b core-c migration-foundation migration-isolation migration-guards; do
    source_file="$repository_root/artifacts/postgres-coverage/$shard/coverage.$shard"
    test -s "$source_file" || {
      echo "Missing coverage data for PostgreSQL shard: $shard" >&2
      return 1
    }
    cp "$source_file" "$combined_directory/coverage.$shard"
  done
}

#============================# MAIN #============================#

trap cleanup EXIT HUP INT TERM

if [ "$parallel_shards" = "auto" ]; then
  docker_cpus=$(docker info --format '{{.NCPU}}')
  docker_memory=$(docker info --format '{{.MemTotal}}')
  if [ "$docker_cpus" -ge 10 ] && [ "$docker_memory" -ge 7000000000 ]; then
    parallel_shards=10
  else
    parallel_shards=5
  fi
fi

case "$parallel_shards" in
  10)
    run_batch core-a core-b core-c route-access route-methods route-session accounts migration-foundation migration-isolation migration-guards
    ;;
  5)
    run_batch core-a core-b core-c accounts migration-foundation
    run_batch route-access route-methods route-session migration-isolation migration-guards
    ;;
  *)
    echo "TEKDOCS_POSTGRES_MATRIX_PARALLEL_SHARDS must be auto, 5, or 10." >&2
    exit 2
    ;;
esac
stage_coverage
"$coverage_merger" "$combined_directory"

echo "Local PostgreSQL test matrix passed"
