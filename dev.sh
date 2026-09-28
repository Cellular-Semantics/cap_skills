#!/usr/bin/env bash
# Set up the package for local development and run its tests.
#
#   ./dev.sh              offline suite, plus the eval graders
#   ./dev.sh -m live      also hit celltype.info
set -euo pipefail
cd "$(dirname "$0")"

uv venv -q --allow-existing packages/cap-client/.venv
uv pip install -q -e "packages/cap-client[test]" --python packages/cap-client/.venv/bin/python
# The eval *graders* are pure and free to test; the eval runs themselves are not
# (real agent runs against celltype.info) and are never part of this script.
packages/cap-client/.venv/bin/python -m pytest packages/cap-client evals "$@"
