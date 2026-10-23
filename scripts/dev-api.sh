#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then set -a; . ./.env; set +a; fi
ROOT_DIR=$(pwd)
cd apps/api
"$ROOT_DIR/.venv/bin/python" -m alembic upgrade head
exec "$ROOT_DIR/.venv/bin/python" -m uvicorn truthhunter.main:app --host 127.0.0.1 --port 8000
