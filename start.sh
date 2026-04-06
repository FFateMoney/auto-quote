#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="$ROOT_DIR/config.yaml"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "未找到配置文件: $CONFIG_PATH" >&2
  exit 1
fi

CONDA_ENV="$(
  awk '
    /^[[:space:]]*startup:/ { in_startup=1; next }
    in_startup && /^[^[:space:]]/ { in_startup=0 }
    in_startup && /^[[:space:]]*conda_env:/ {
      sub(/.*conda_env:[[:space:]]*/, "", $0)
      gsub(/["'\''"]/, "", $0)
      print $0
      exit
    }
  ' "$CONFIG_PATH"
)"

CONDA_ENV="${CONDA_ENV:-quote}"

cd "$ROOT_DIR"
exec conda run --no-capture-output -n "$CONDA_ENV" python start.py
