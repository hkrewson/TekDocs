#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
coverage_directory=${1:-"$repository_root/artifacts/postgres-coverage/combined"}

case "$coverage_directory" in
  /*) ;;
  *) coverage_directory="$repository_root/$coverage_directory" ;;
esac

for shard in route-access route-methods route-session remaining; do
  test -s "$coverage_directory/coverage.$shard" || {
    echo "Missing coverage data for PostgreSQL shard: $shard" >&2
    exit 1
  }
done

rm -f "$coverage_directory/coverage"
chmod 0777 "$coverage_directory"
docker build --target development --tag tekdocs-postgres-coverage "$repository_root/backend" >/dev/null
docker run --rm \
  -v "$coverage_directory:/coverage" \
  -e COVERAGE_FILE=/coverage/coverage \
  tekdocs-postgres-coverage \
  sh -c 'coverage combine /coverage && coverage report --fail-under=80'

echo "Combined PostgreSQL shard coverage passed"
