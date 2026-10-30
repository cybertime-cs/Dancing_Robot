#!/usr/bin/env bash
# 统一启动；所有参数交给 main.py，包括 --check / --dry-run / --action。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$PROJECT_DIR/runtime.env" ]; then
  set -a
  source "$PROJECT_DIR/runtime.env"
  set +a
fi
export PYTHONUNBUFFERED=1
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
PY="${PYTHON_BIN:-python3}"
if [ -x "$VENV_DIR/bin/python" ]; then PY="$VENV_DIR/bin/python"; fi
# 纯检查和纯模拟可与后台服务并行；实际录音/播放/串口入口只允许一份。
NEEDS_LOCK=1
for ARG in "$@"; do
  case "$ARG" in --check|--list-actions|--dry-run) NEEDS_LOCK=0 ;; esac
done
if [ "$NEEDS_LOCK" = 1 ]; then
  exec 9>"$PROJECT_DIR/.runtime.lock"
  if ! flock -n 9; then
    printf '已有机器人程序正在运行；手动排练前先执行 systemctl --user stop fenghou.service。\n' >&2
    exit 73
  fi
fi
exec "$PY" "$PROJECT_DIR/main.py" "$@"
