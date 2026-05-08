#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

SERVICE="${1:-}"
if [ -z "$SERVICE" ]; then
  echo "usage: $0 {quote|ocr|cleaning|indexing} [--print]" >&2
  exit 2
fi
MODE="${2:-}"

CONFIG_PATH="${AUTO_QUOTE_CONFIG_PATH:-$ROOT_DIR/backend/dev/config.yaml}"
CONDA_ENV=""

if [ -f "$CONFIG_PATH" ]; then
  CONDA_ENV="$(python - <<'PY' "$CONFIG_PATH"
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
startup = data.get("startup") or {}
value = startup.get("conda_env") or ""
print(str(value).strip())
PY
)"
fi

read -r APP HOST PORT < <(python - <<'PY' "$SERVICE"
import sys

service = sys.argv[1]
if service == "quote":
    from backend.quote.settings import get_settings
    s = get_settings()
    print(f"backend.quote.http.app:app {s.host} {s.port}")
elif service == "ocr":
    from backend.ocr.settings import get_settings
    s = get_settings()
    print(f"backend.ocr.http.app:app {s.host} {s.port}")
elif service == "cleaning":
    from backend.cleaning.settings import get_settings
    s = get_settings()
    print(f"backend.cleaning.http.app:app {s.host} {s.port}")
elif service == "indexing":
    from backend.indexing.settings import get_settings
    s = get_settings()
    print(f"backend.indexing.http.app:app {s.host} {s.port}")
else:
    raise SystemExit(f"unknown service: {service}")
PY
)

echo "Starting $SERVICE service on $HOST:$PORT"

if [ "$MODE" = "--print" ]; then
  echo "python -m uvicorn $APP --host $HOST --port $PORT"
  exit 0
fi

if [ -n "$CONDA_ENV" ] && command -v conda >/dev/null 2>&1; then
  exec conda run --no-capture-output -n "$CONDA_ENV" python -m uvicorn "$APP" --host "$HOST" --port "$PORT"
fi

exec python -m uvicorn "$APP" --host "$HOST" --port "$PORT"
