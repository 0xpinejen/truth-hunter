#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
ROOT_DIR=$(pwd)
cd apps/api
PYTHONPATH=. "$ROOT_DIR/.venv/bin/python" -m pytest tests -q
cd ../web
npm run typecheck
npm run build
