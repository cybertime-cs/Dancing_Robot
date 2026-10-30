#!/usr/bin/env bash
# 服务入口：等待外设和音频，启动连续多轮演出。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$PROJECT_DIR/runtime.env" ]; then
  set -a
  source "$PROJECT_DIR/runtime.env"
  set +a
fi
export PYTHONUNBUFFERED=1
PY="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
if [ -x "$VENV_DIR/bin/python" ]; then PY="$VENV_DIR/bin/python"; fi
"$PY" "$SCRIPT_DIR/pi_service_prepare.py"
exec bash "$SCRIPT_DIR/pi_run.sh" --repeat
