#!/usr/bin/env bash
# Set up both packages for local development and run their test suites.
#
# h5ad-obs depends on cap-client by git tag -- that is what a user installing the
# plugin gets -- so locally it is installed with --no-deps over an editable
# cap-client, and its runtime dependencies are installed by hand. Otherwise every
# local test run would resolve against a published tag instead of the working tree.
set -euo pipefail
cd "$(dirname "$0")"

echo "== cap-client"
uv venv -q --allow-existing packages/cap-client/.venv
uv pip install -q -e "packages/cap-client[test]" --python packages/cap-client/.venv/bin/python
# The eval *graders* are pure and free to test; the eval runs themselves are not
# (real agent runs against celltype.info) and are never part of this script.
packages/cap-client/.venv/bin/python -m pytest packages/cap-client evals "$@"

echo "== h5ad-obs"
uv venv -q --allow-existing packages/h5ad-obs/.venv
PY=packages/h5ad-obs/.venv/bin/python
uv pip install -q --python "$PY" -e packages/cap-client
uv pip install -q --python "$PY" fsspec aiohttp h5py numpy pandas pyarrow certifi pytest
uv pip install -q --python "$PY" --no-deps -e packages/h5ad-obs
"$PY" -m pytest packages/h5ad-obs "$@"
