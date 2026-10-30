"""统一运行日志；正常模式只显示进度、结果和可处理的问题。"""
from datetime import datetime, timezone, timedelta
import os
import threading

_lock = threading.Lock()


def event(category, message, *, debug=False):
    if debug and os.getenv('ROBOT_DEBUG', '') != '1':
        return
    with _lock:
        print('[%s] [%s] %s' % (datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S'), category, message), flush=True)
