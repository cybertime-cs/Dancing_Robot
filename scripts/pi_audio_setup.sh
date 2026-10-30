#!/usr/bin/env bash
# ============================================================================
# 麦克风诊断 / 修复（树莓派 5，Raspberry Pi OS）
#
#   bash scripts/pi_audio_setup.sh              # 诊断：有哪些录音设备、支持哪些采样率
#   bash scripts/pi_audio_setup.sh --fix        # 额外准备一个 pcm.mic16k（给 arecord 等命令行工具）
#   bash scripts/pi_audio_setup.sh --fix --set-default   # 连系统默认设备也改成这个麦克风
#   bash scripts/pi_audio_setup.sh --remove     # 撤销本脚本写入的 ~/.asoundrc 片段
#
# 为什么需要这个脚本：
#   不少 USB 麦克风/声卡**只支持 44100 或 48000 Hz**。程序里直接以 rate=16000 开流
#   会被 ALSA 拒掉，PyAudio 抛
#       OSError: [Errno -9997] Invalid sample rate
#   而这个报错只指向 pyaudio 内部（前面还有一屏 JACK/ALSA 噪音），
#   完全看不出是「这台麦克风不支持 16kHz」。
#
#   **程序本身已经不需要任何配置**：audio.open_input_stream() 会自己协商采样率，
#   必要时把 44.1k/48k 在软件里重采样回 16kHz（唤醒与录音共用这套逻辑）。
#   本脚本的作用是把「到底发生了什么」讲清楚，并给命令行工具（arecord/mplayer）
#   留一个能用的 16kHz 入口。
#
# 安全说明：--fix 只**追加**一个带标记的片段到 ~/.asoundrc，不会覆盖你已有的配置；
#   写入前会先备份。--remove 只删掉这个片段，不动其它内容。
#
# 参数：
#   --list           只列设备，不做完整性检查
#   --fix            写入 pcm.mic16k（type plug，自动转换到 16kHz）
#   --set-default    配合 --fix：把 pcm.!default 也指向该麦克风
#                    （注意：会同时影响**播放**，若该声卡没有输出能力会放不出声音）
#   --card N         指定声卡号（默认自动挑：优先有录音能力的那张）
#   --device N       指定设备号，默认 0
#   --remove         移除本脚本写入的片段
#   -h, --help       查看帮助
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

ASOUNDRC="$HOME/.asoundrc"
MARK_BEGIN="# >>> pi_audio_setup (dancing_robot) >>>"
MARK_END="# <<< pi_audio_setup (dancing_robot) <<<"
TARGET_RATE=16000

DO_FIX=0; DO_REMOVE=0; SET_DEFAULT=0; LIST_ONLY=0
CARD=""; DEVICE=""

c_info='\033[36m'; c_ok='\033[32m'; c_warn='\033[33m'; c_err='\033[31m'; c_rst='\033[0m'
step() { printf '\n%b==>%b %s\n' "$c_info" "$c_rst" "$*"; }
ok()   { printf '%b  ✔%b %s\n' "$c_ok" "$c_rst" "$*"; }
warn() { printf '%b  ! %b %s\n' "$c_warn" "$c_rst" "$*"; }
err()  { printf '%b  ✘ %b %s\n' "$c_err" "$c_rst" "$*" >&2; }

usage() { awk 'NR>1 && /^set -euo/{exit} NR>1{sub(/^# ?/,""); print}' "$0"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --list) LIST_ONLY=1 ;;
    --fix) DO_FIX=1 ;;
    --remove) DO_REMOVE=1 ;;
    --set-default) SET_DEFAULT=1 ;;
    --card)
      CARD="${2:-}"; [ -n "$CARD" ] || { err "--card 需要一个声卡号"; exit 2; }
      shift ;;
    --device)
      DEVICE="${2:-}"; [ -n "$DEVICE" ] || { err "--device 需要一个设备号"; exit 2; }
      shift ;;
    -h|--help) usage; exit 0 ;;
    *) err "未知参数：$1"; echo; usage; exit 2 ;;
  esac
  shift
done

have() { command -v "$1" >/dev/null 2>&1; }

printf '%b\n' "════════════════════════════════════════════════════════════"
printf '  麦克风诊断  ·  目标采样率：%dHz\n' "$TARGET_RATE"
printf '%b\n' "════════════════════════════════════════════════════════════"

# ---- 0. 依赖 ---------------------------------------------------------------
if ! have arecord; then
  err "找不到 arecord（alsa-utils）。先装：sudo apt install -y alsa-utils mplayer ffmpeg"
  exit 1
fi
have mplayer >/dev/null 2>&1 || have ffplay >/dev/null 2>&1 || \
  warn "mplayer / ffplay 都没有，程序放不出提示音与配音（sudo apt install -y mplayer ffmpeg）"

# ---- 1. 列出设备 -----------------------------------------------------------
step "1/4 系统识别到的声卡"
arecord -l 2>/dev/null || warn "arecord -l 执行失败"
if have aplay; then
  printf '\n  --- 播放设备（aplay -l）---\n'
  aplay -l 2>/dev/null || true
fi

# 解析 arecord -l：输出每行一条 "card|device|描述"
#
# 注意设备号**不能**用 $2 取：`card 2: ... , device 0: ...` 这一行同时以 "card" 开头，
# $2 是卡号而不是设备号，会把 hw:2,0 解析成 hw:2,2（一个不存在的设备）。
# 所以一律从整行里用 sub() 抠数字，让两个规则互不干扰。
#
# 这段程序被 scripts/selftest.py 第 11 节抽出来单独跑（含真机那一行的回归），
# 改动时请连同那边的期望值一起改。
# >>> awk: parse arecord -l >>>
ARECORD_LIST_AWK='
  /^card [0-9]+:/ {
    card = $0; sub(/^card /, "", card); sub(/:.*/, "", card)
    cname = $0; sub(/^card [0-9]+: /, "", cname); sub(/, device .*/, "", cname)
    sub(/\[.*$/, "", cname); sub(/ +$/, "", cname)
  }
  /device [0-9]+:/ {
    dev = $0; sub(/^.*device /, "", dev); sub(/:.*/, "", dev)
    dname = $0; sub(/^.*device [0-9]+: /, "", dname); sub(/\[.*$/, "", dname)
    sub(/ +$/, "", dname)
    printf "%s|%s|%s / %s\n", card, dev, cname, dname
  }
'
# <<< awk: parse arecord -l <<<

mapfile -t CAPTURE_DEVICES < <(arecord -l 2>/dev/null | awk "$ARECORD_LIST_AWK")

if [ "${#CAPTURE_DEVICES[@]}" -eq 0 ]; then
  err "没有检测到任何录音设备。"
  echo "      树莓派 5 本身没有模拟音频输入，必须外接麦克风："
  echo "        · USB 麦克风 / USB 声卡：直接插 USB 口，然后重插一次让它重新枚举"
  echo "        · 插好后重跑本脚本确认：bash scripts/pi_audio_setup.sh"
  exit 1
fi
echo
printf '  共 %d 个录音设备：\n' "${#CAPTURE_DEVICES[@]}"
for entry in "${CAPTURE_DEVICES[@]}"; do
  IFS='|' read -r c d desc <<<"$entry"
  printf '    card %s, device %s  — %s\n' "$c" "$d" "$desc"
done

if [ "$LIST_ONLY" = "1" ]; then
  echo
  ok "仅列出设备（--list），未做采样率检查"
  exit 0
fi

# ---- 2. 逐个设备读真实支持的采样率 ----------------------------------------
# 用 arecord --dump-hw-params 直接向 ALSA **问**设备的 HW 参数，
# 比「真录 1 秒看成不成」快得多，也能拿到完整的 RATE 范围。
#
# **必须带 -d <秒>。** `--dump-hw-params` 本身不结束录音 —— 参数打印完之后
# arecord 会一直录下去，脚本就此卡死（2026-09-30 真机上正是如此：
# 走到 "2/4" 就不动了，只能 ^C）。给个 1 秒的上限即可，参数在开始录之前就拿到了。
step "2/4 各设备支持的采样率（问 ALSA 要 HW 参数）"

native_16k=""      # 原生支持 16kHz 的设备，形如 "card|device"
_fallback_dev=""   # 退路：不原生支持 16kHz、但至少能打开的设备
busy_devices=()
for entry in "${CAPTURE_DEVICES[@]}"; do
  IFS='|' read -r c d desc <<<"$entry"
  stream="hw:${c},${d}"
  dump="$(arecord -D "$stream" --dump-hw-params -f S16_LE -d 1 /dev/null 2>&1 || true)"
  rate_line="$(printf '%s\n' "$dump" | grep -m1 '^RATE:' || true)"
  chan_line="$(printf '%s\n' "$dump" | grep -m1 '^CHANNELS:' || true)"

  printf '\n  [%s] %s\n' "$stream" "$desc"
  if [ -z "$rate_line" ]; then
    # arecord 的报错未必带 "busy"/"no such device" 字样（例如
    # "audio open error: No such file or directory"），所以取第一条含 error 的行，
    # 取不到就取第一条非空行 —— 总之要把原因露出来，不要让用户对着"失败"干猜。
    reason="$(printf '%s\n' "$dump" | grep -m1 -i 'error' || true)"
    if [ -z "$reason" ]; then
      reason="$(printf '%s\n' "$dump" | grep -m1 . || true)"
    fi
    printf '      读取 HW 参数失败：%s\n' "${reason:-原因未知}"
    if printf '%s' "$reason" | grep -qi 'busy'; then
      busy_devices+=("$stream")
      warn "该设备正被占用（可能有程序在录音）"
    fi
    continue
  fi

  printf '      %s\n' "${rate_line#RATE: }"
  if [ -n "$chan_line" ]; then printf '      %s\n' "$chan_line"; fi

  # RATE 有两种形式：  "RATE: [16000 48000]"   或   "RATE: 16000"
  if printf '%s' "$rate_line" | grep -q '\[.*\]'; then
    lo="$(printf '%s' "$rate_line" | sed -E 's/.*\[([0-9]+) +([0-9]+)\].*/\1/')"
    hi="$(printf '%s' "$rate_line" | sed -E 's/.*\[([0-9]+) +([0-9]+)\].*/\2/')"
  else
    lo="$(printf '%s' "$rate_line" | sed -E 's/[^0-9]*([0-9]+).*/\1/')"
    hi="$lo"
  fi

  if [ -n "$lo" ] && [ -n "$hi" ] && [ "$lo" -le "$TARGET_RATE" ] && [ "$TARGET_RATE" -le "$hi" ]; then
    ok "原生支持 ${TARGET_RATE}Hz —— 程序直接可用，不需要任何处理"
    if [ -z "$native_16k" ]; then native_16k="${c}|${d}"; fi
  else
    warn "不支持 ${TARGET_RATE}Hz（范围 ${lo}~${hi}）—— 程序会自动重采样，无需处理"
    if [ -z "$native_16k" ] && [ -z "$_fallback_dev" ]; then _fallback_dev="${c}|${d}"; fi
  fi
done

# ---- 3. 拿程序真正用的那套枚举看一眼 --------------------------------------
step "3/4 PortAudio（程序实际用的接口）看到什么"
PYTHON_BIN=""
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
elif have python3; then
  PYTHON_BIN="python3"
fi

if [ -n "$PYTHON_BIN" ]; then
  "$PYTHON_BIN" - <<'PY' || warn "列 PortAudio 设备失败（可能 pyaudio 没装到该解释器）"
import ctypes
import sys

# 先把 ALSA 的错误处理器换掉：枚举设备时 ALSA 会往 stderr 打几十行
# "Unknown PCM front / surround51 / jack server is not running" 之类的噪音，
# 那是**探测过程的正常产物**，看起来却像一大堆故障。
# 保留引用，别让回调对象被 GC（ALSA 仍持有它）。
_asound = _handler = None
try:
    _asound = ctypes.cdll.LoadLibrary("libasound.so")
    _CB = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int,
                           ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
    _handler = _CB(lambda *a: None)
    _asound.snd_lib_error_set_handler(_handler)
except Exception:
    pass

try:
    import pyaudio
except Exception as exc:
    print("      未安装 pyaudio（%s）—— 先跑 bash scripts/pi_setup.sh" % exc)
    sys.exit(0)

pa = pyaudio.PyAudio()
print("      %-4s %-38s %-8s %s" % ("索引", "名称", "输入声道", "默认采样率"))
try:
    default_index = pa.get_default_input_device_info()["index"]
except Exception:
    default_index = None
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if int(info.get("maxInputChannels") or 0) <= 0:
        continue
    mark = " ← 默认" if i == default_index else ""
    print("      %-4d %-38s %-8d %s%s" % (
        i, str(info.get("name"))[:38], int(info.get("maxInputChannels")),
        int(info.get("defaultSampleRate") or 0), mark))
if default_index is None:
    print("      注意：系统没有默认输入设备，程序会自己扫描可录音的设备")
pa.terminate()
PY
else
  warn "找不到可用的 python"
fi

# ---- 4. 结论 / 可选修复 ----------------------------------------------------
step "4/4 结论"

if [ "$DO_REMOVE" = "1" ]; then
  if [ ! -f "$ASOUNDRC" ] || ! grep -qF "$MARK_BEGIN" "$ASOUNDRC"; then
    ok "~/.asoundrc 里没有本脚本写入的片段，无需处理"
    exit 0
  fi
  tmp="$(mktemp)"
  awk -v b="$MARK_BEGIN" -v e="$MARK_END" '
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    !skip { print }
  ' "$ASOUNDRC" > "$tmp"
  cp -p "$ASOUNDRC" "$ASOUNDRC.bak.$(date +%Y%m%d%H%M%S)"
  mv "$tmp" "$ASOUNDRC"
  ok "已移除片段（原文件已备份为 $ASOUNDRC.bak.*）"
  exit 0
fi

if [ -n "$native_16k" ]; then
  IFS='|' read -r nc nd <<<"$native_16k"
  ok "有设备原生支持 ${TARGET_RATE}Hz（card ${nc}, device ${nd}）"
  echo "      程序可以直接用：bash scripts/pi_run.sh"
  echo "      若有多个麦克风、想固定用这一个，找出它的 PortAudio 索引（见上一节）后设："
  echo "        MIC_DEVICE=<索引> bash scripts/pi_run.sh"
else
  warn "没有任何设备原生支持 ${TARGET_RATE}Hz —— 这正是 '[Errno -9997] Invalid sample rate' 的原因"
  echo "      程序已内置处理：会自动按设备支持的采样率开流，再在软件里重采样到 16kHz，"
  echo "      唤醒与录音都走这套逻辑，因此**不需要任何配置**，直接："
  echo "        bash scripts/pi_run.sh"
  echo "      只有在你还想让 arecord 等命令行工具直接录 16kHz 时，才需要下面这一步。"
fi

if [ "${#busy_devices[@]}" -gt 0 ]; then
  echo
  warn "以下设备正被占用，可能影响测试结果：${busy_devices[*]}"
  echo "      确认没有其它程序在录音（例如上一个 make run 没退干净）。"
fi

if [ "$DO_FIX" != "1" ]; then
  if [ -z "$native_16k" ]; then
    echo
    echo "  可选：bash scripts/pi_audio_setup.sh --fix"
    echo "        在 ~/.asoundrc 里追加一个 pcm.mic16k（type plug，自动转换到 16kHz），"
    echo "        之后 arecord -D mic16k 就能直接录 16kHz。不会影响程序本身。"
  fi
  exit 0
fi

# 选定要写入的声卡
if [ -n "$CARD" ]; then
  SEL_CARD="$CARD"
  SEL_DEVICE="${DEVICE:-0}"
elif [ -n "$native_16k" ]; then
  IFS='|' read -r SEL_CARD SEL_DEVICE _ <<<"$native_16k"
elif [ -n "$_fallback_dev" ]; then
  IFS='|' read -r SEL_CARD SEL_DEVICE _ <<<"$_fallback_dev"
else
  # 一个都读不到 HW 参数（可能全被占用）：退回第一个设备
  IFS='|' read -r SEL_CARD SEL_DEVICE _ <<<"${CAPTURE_DEVICES[0]}"
fi
if [ -n "${DEVICE:-}" ]; then SEL_DEVICE="$DEVICE"; fi

SLAVE="hw:${SEL_CARD},${SEL_DEVICE}"
printf '\n  将使用 %s\n' "$SLAVE"

# 写进 ~/.asoundrc 之前先确认这个设备真的打得开 ——
# 否则就会留下一个指向不存在设备的 pcm.mic16k（2026-09-30 真机上正是如此：
# 设备号被解析成 2，于是写了 slave.pcm "hw:2,2"，PortAudio 里还多出一个假的 mic16k）。
# 同样带 -d 1 封顶，否则这一步也会一直录下去。
if ! arecord -D "$SLAVE" --dump-hw-params -f S16_LE -d 1 /dev/null >/dev/null 2>&1; then
  err "$SLAVE 打不开，**不写入配置**（免得留下一个坏的 pcm.mic16k）"
  echo "      先确认设备号：bash scripts/pi_audio_setup.sh --list"
  echo "      或显式指定：bash scripts/pi_audio_setup.sh --fix --card N --device M"
  echo "      清掉可能已存在的旧片段：bash scripts/pi_audio_setup.sh --remove"
  exit 1
fi
ok "确认 $SLAVE 可以打开"

block="$(mktemp)"
{
  printf '%s\n' "$MARK_BEGIN"
  printf '# 由 scripts/pi_audio_setup.sh 生成于 %s\n' "$(date '+%Y-%m-%d %H:%M:%S')"
  printf '# pcm.mic16k：以 plug 包一层，让 16kHz 请求自动转换到设备真实支持的采样率。\n'
  printf 'pcm.mic16k {\n    type plug\n    slave.pcm "%s"\n}\n' "$SLAVE"
  if [ "$SET_DEFAULT" = "1" ]; then
    printf '# 注意：pcm.!default 同时影响**播放**。若 %s 没有输出能力，改完会放不出声音。\n' "$SLAVE"
    printf 'pcm.!default {\n    type plug\n    slave.pcm "%s"\n}\n' "$SLAVE"
  fi
  printf '%s\n' "$MARK_END"
} > "$block"

if [ "$SET_DEFAULT" = "1" ]; then
  warn "--set-default 会同时改变播放设备；若该声卡没有输出能力，程序会放不出提示音与配音。"
fi

# 幂等：先去掉旧片段，再追加新片段；原文件先备份
if [ -f "$ASOUNDRC" ]; then
  cp -p "$ASOUNDRC" "$ASOUNDRC.bak.$(date +%Y%m%d%H%M%S)"
  ok "已备份原有 $ASOUNDRC"
  tmp="$(mktemp)"
  awk -v b="$MARK_BEGIN" -v e="$MARK_END" '
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    !skip { print }
  ' "$ASOUNDRC" > "$tmp"
  cat "$block" >> "$tmp"
  mv "$tmp" "$ASOUNDRC"
else
  cat "$block" > "$ASOUNDRC"
fi
rm -f "$block"
ok "已写入 $ASOUNDRC"

# 验证：让 arecord 用这个名字录 1 秒 16kHz
if arecord -D mic16k -r "$TARGET_RATE" -f S16_LE -c 1 -d 1 -t raw /dev/null >/dev/null 2>&1; then
  ok "验证通过：arecord -D mic16k -r ${TARGET_RATE} 可以录音"
else
  warn "验证未通过：arecord -D mic16k 仍失败，用下面这条看具体原因"
  echo "      arecord -D mic16k -r ${TARGET_RATE} -f S16_LE -c 1 -d 1 -t raw /dev/null"
fi

echo
echo "  撤销：bash scripts/pi_audio_setup.sh --remove"
