#!/usr/bin/env bash
# 在树莓派运行：配置当前用户开机服务并启动，不推送 GitHub。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ "$PROJECT_DIR" == *'%'* || "$PROJECT_DIR" == *'"'* || "$PROJECT_DIR" == *$'\n'* ]]; then
  printf '服务路径不能含百分号、双引号或换行。\n' >&2
  exit 1
fi
mkdir -p "$HOME/.config/systemd/user"
PROJECT_DIR="$PROJECT_DIR" python3 - <<'PY'
import os
from pathlib import Path
root=Path(os.environ['PROJECT_DIR'])
template=(root/'services/fenghou.service.in').read_text()
target=Path.home()/'.config/systemd/user/fenghou.service'
target.write_text(template.replace('@PROJECT_DIR@',str(root)))
PY
loginctl enable-linger "$(id -un)"
systemd-analyze --user verify "$HOME/.config/systemd/user/fenghou.service"
systemctl --user daemon-reload
systemctl --user enable --now fenghou.service
systemctl --user status fenghou.service --no-pager
