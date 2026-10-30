#!/bin/sh
# Run from the delivered project. The API remains on loopback behind HTTPS.
set -eu
cd "$(dirname "$0")/../backend"
export LIFE_REQUEST_WORKERS="${LIFE_REQUEST_WORKERS:-4}"
export LIFE_DEVELOPMENT_MODE="${LIFE_DEVELOPMENT_MODE:-0}"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${LIFE_API_PORT:-8000}" --workers 1 --limit-concurrency 32 --backlog 64 --timeout-keep-alive 3
