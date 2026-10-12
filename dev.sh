#!/usr/bin/env bash
# Set up the package for local development and run every offline check CI runs.
#
#   ./dev.sh              offline suite, the eval graders and the release tooling
#   ./dev.sh -m live      also hit celltype.info
set -euo pipefail
cd "$(dirname "$0")"

uv venv -q --allow-existing packages/cap-client/.venv
uv pip install -q -e "packages/cap-client[test]" --python packages/cap-client/.venv/bin/python
# The eval *graders* are pure and free to test; the eval runs themselves are not
# (real agent runs against celltype.info) and are never part of this script.
packages/cap-client/.venv/bin/python -m pytest packages/cap-client evals "$@"
# The release tooling, against throwaway git repos.
packages/cap-client/.venv/bin/python -m pytest tests -q
python3 scripts/versions.py report --check docs/pins.md
if command -v claude >/dev/null; then
  claude plugin validate . && for p in plugins/*/; do claude plugin validate "$p"; done
fi
