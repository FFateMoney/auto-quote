#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

MODE="${1:-sync}"
shift || true

case "$MODE" in
  sync)
    OCR_ARGS=(sync)
    ;;
  rebuild)
    OCR_ARGS=(rebuild)
    ;;
  *)
    echo "Usage: ./run_ocr_markdown.sh [sync|rebuild]" >&2
    exit 1
    ;;
esac

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

if [ -n "$CONDA_ENV" ] && command -v conda >/dev/null 2>&1; then
  exec conda run --no-capture-output -n "$CONDA_ENV" python -m backend.ocr.cli "${OCR_ARGS[@]}" "$@"
fi

exec python -m backend.ocr.cli "${OCR_ARGS[@]}" "$@"
