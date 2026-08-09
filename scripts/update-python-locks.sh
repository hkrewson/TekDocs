#!/bin/sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tool_dir=$(mktemp -d "${TMPDIR:-/tmp}/tekdocs-pip-tools.XXXXXX")
trap 'rm -rf "$tool_dir"' EXIT INT TERM

python_image='python:3.13.11-slim-bookworm@sha256:20080e807bfc404f8450b185cf0fc95d553462673598549613735f70a5b4d5d0'
docker run --rm -v "$tool_dir:/tools" "$python_image" \
  python -m pip install --target /tools 'pip==25.3' 'pip-tools==7.5.2'

compile() {
  docker run --rm -e PYTHONPATH=/tools \
    -v "$tool_dir:/tools:ro" -v "$root_dir/backend:/workspace" -w /workspace \
    "$python_image" python -m piptools compile "$@"
}

compile build-requirements.in --output-file build-requirements.lock \
  --generate-hashes --strip-extras --allow-unsafe --resolver backtracking --quiet
compile pyproject.toml --output-file requirements.lock \
  --generate-hashes --strip-extras --allow-unsafe --resolver backtracking --quiet
compile pyproject.toml --extra dev --output-file requirements-dev.lock \
  --generate-hashes --strip-extras --allow-unsafe --resolver backtracking --quiet
