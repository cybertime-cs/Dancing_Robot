"""媒体时长索引和独立播放计时，串口等待不会污染播放耗时。"""
import json
from functools import lru_cache
from pathlib import Path
import subprocess
import threading
import time
from runtime_log import event

ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _index():
    try:
        return json.loads((ROOT/'audio_durations.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def duration(path):
    try:
        file = Path(path).resolve()
        item = _index().get(file.relative_to(ROOT).as_posix(), {})
        return item.get('seconds') if item.get('size') == file.stat().st_size else None
    except (ValueError, OSError):
        return None


class PlaybackMonitor:
    def __init__(self, process, name, total, timeout):
        self.process, self.name, self.total = process, name, total
        self.timeout = timeout
        self.started = time.monotonic()
        self.elapsed = None
        self.error = None
        self.cancelled = False
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._watch, daemon=True)
        self.thread.start()

    def _watch(self):
        try:
            code = self.process.wait(timeout=self.timeout)
            if code != 0:
                raise RuntimeError('音频播放失败，退出码 %s' % code)
        except subprocess.TimeoutExpired:
            self.error = RuntimeError('音频播放超时')
        except BaseException as exc:
            self.error = exc
        finally:
            self.elapsed = time.monotonic() - self.started
            status = '已中断' if self.cancelled else '失败' if self.error else '完成'
            total = '未知' if self.total is None else '%.2f 秒' % self.total
            event('音频', '%s | %s | 总时长 %s | 实际耗时 %.2f 秒' % (self.name, status, total, self.elapsed))
            self.done.set()

    def wait(self):
        while not self.done.wait(.1):
            pass
        if self.error:
            raise self.error
