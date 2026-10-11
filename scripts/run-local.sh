#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo 'Создайте .venv и установите requirements.txt (см. README).' >&2
  exit 1
fi
export APP_ENV="${APP_ENV:-development}"
export PORT="${PORT:-8080}"
export APP_ORIGIN="${APP_ORIGIN:-http://localhost:$PORT}"
exec .venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port "$PORT" --workers 1 --no-access-log
