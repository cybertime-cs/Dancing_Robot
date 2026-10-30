#!/usr/bin/env bash
# 部署蜂后演出所需依赖。默认只装唤醒、识别、音频与串口。
# 参数：--cn-mirror --models-from DIR --skip-apt --skip-pip --skip-sherpa
# 旧参数 --minimal / --fast 仍接受，当前默认已经是精简部署。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SKIP_APT=0; SKIP_PIP=0; SKIP_MODELS=0; MODELS_FROM=""
INDEX="https://pypi.org/simple"
FALLBACK="https://pypi.tuna.tsinghua.edu.cn/simple"
while [ $# -gt 0 ]; do
  case "$1" in
    --minimal|--fast) ;;
    --cn-mirror) INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"; FALLBACK="https://pypi.org/simple" ;;
    --skip-apt) SKIP_APT=1 ;;
    --skip-pip) SKIP_PIP=1 ;;
    --skip-sherpa) SKIP_MODELS=1 ;;
    --models-from) MODELS_FROM="${2:?--models-from 需要目录}"; shift ;;
    -h|--help) head -n 4 "$0"; exit 0 ;;
    *) printf '未知参数：%s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done
if [ "$SKIP_APT" = 0 ]; then
  SUDO=()
  if [ "$(id -u)" != 0 ]; then SUDO=(sudo); fi
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y mplayer ffmpeg alsa-utils python3-venv python3-pip python3-dev build-essential portaudio19-dev
fi
if [ ! -x "$VENV_DIR/bin/python" ]; then "$PYTHON_BIN" -m venv "$VENV_DIR"; fi
PY="$VENV_DIR/bin/python"
if [ "$SKIP_PIP" = 0 ]; then
  # 清空系统额外索引，避免安装过程反复连接不可用的 piwheels。
  cat > "$VENV_DIR/pip.conf" <<EOF
[global]
index-url = $INDEX
extra-index-url =
timeout = 20
retries = 3
EOF
  export PIP_CONFIG_FILE="$VENV_DIR/pip.conf"
  "$PY" -m pip install -U pip setuptools wheel || printf 'pip 升级失败，继续用现有版本。\n' >&2
  "$PY" -m pip install -r requirements.txt || "$PY" -m pip install -i "$FALLBACK" -r requirements.txt
fi
if [ "$SKIP_MODELS" = 0 ]; then
  MODEL_ARGS=()
  if [ -n "$MODELS_FROM" ]; then MODEL_ARGS=(--from "$MODELS_FROM"); fi
  "$PY" scripts/prepare_sherpa_models.py "${MODEL_ARGS[@]}"
fi
"$PY" scripts/selftest.py
"$PY" scripts/pi_doctor.py
printf '\n软件检查通过。现场检查：%s scripts/pi_doctor.py --hardware\n' "$PY"
printf '串口请在 raspi-config 中开启 UART、关闭串口登录，重启后确认权限。\n'
printf '演出：bash scripts/pi_run.sh；模拟：bash scripts/pi_run.sh --dry-run --demo\n'
