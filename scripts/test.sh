#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
ROOT_DIR=$(pwd)
node --test deploy/edgeone/tests/gateway.test.mjs
cd apps/api
PYTHONPATH=. "$ROOT_DIR/.venv/bin/python" -m pytest tests -q
cd ../web
npm run typecheck
npm run test:showcase
npm run build
