#!/usr/bin/env bash
# 可选连接已配对的音箱，然后进入蜂后演出。未配置 BT_MAC 时使用系统默认输出。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${BT_MAC:-}" ] && [ "${ENABLE_BLUETOOTH:-1}" = "1" ]; then
  bluetoothctl connect "$BT_MAC" || printf '音箱连接失败，请检查系统默认音频输出。\n' >&2
fi
exec bash "$SCRIPT_DIR/pi_run.sh" "$@"
