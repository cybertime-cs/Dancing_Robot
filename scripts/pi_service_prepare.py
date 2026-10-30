"""开机等待指定输出、麦克风与串口；不播放、不下发动作。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime_log import event


def prepare_once(output_name, volume):
    result = subprocess.run(['pw-dump'], capture_output=True, text=True, timeout=10, check=True)
    nodes = json.loads(result.stdout)
    sinks = []
    for node in nodes:
        props = (node.get('info') or {}).get('props') or {}
        if props.get('media.class') == 'Audio/Sink' and output_name.casefold() in str(props.get('node.description', '')).casefold():
            sinks.append(node)
    if len(sinks) != 1:
        raise RuntimeError('指定音频输出 %s 匹配 %d 个设备' % (output_name, len(sinks)))
    sink_id = str(sinks[0]['id'])
    for command in (['wpctl', 'set-default', sink_id], ['wpctl', 'set-mute', sink_id, '0'],
                    ['wpctl', 'set-volume', sink_id, str(volume)]):
        subprocess.run(command, capture_output=True, text=True, timeout=10, check=True)
    check = subprocess.run([sys.executable, str(ROOT/'scripts/pi_doctor.py'), '--hardware'],
                           capture_output=True, text=True, timeout=40)
    if check.returncode:
        failures = [line for line in check.stdout.splitlines() if line.startswith('[失败]')]
        raise RuntimeError('; '.join(failures) or check.stderr.strip() or '硬件检查未通过')


def main():
    output_name = os.getenv('AUDIO_OUTPUT_NAME', 'KT USB Audio').strip()
    try:
        volume = float(os.getenv('AUDIO_VOLUME', '0.8'))
        if not output_name or not 0 <= volume <= 1:
            raise ValueError('AUDIO_OUTPUT_NAME 不能为空，AUDIO_VOLUME 必须在 0～1 之间')
    except ValueError as exc:
        event('自启动', '配置错误：%s' % exc)
        return 1
    deadline = time.monotonic() + 120
    while True:
        try:
            prepare_once(output_name, volume)
            event('自启动', '外设就绪 | 输出 %s | 音量 %.0f%%' % (output_name, volume*100))
            return 0
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            event('自启动', '等待外设：%s' % exc)
            if time.monotonic() >= deadline:
                event('自启动', '本次等待超时，服务稍后重新检查')
                return 75
            time.sleep(5)


if __name__ == '__main__':
    raise SystemExit(main())
