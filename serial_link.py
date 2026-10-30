# serial_link.py
"""与下位机的串口链路：连接复用、发送数据帧、等待应答。

整理前每个动作都会开关一次 /dev/ttyAMA0，且串口异常会直接抛出到唤醒循环里
把整个程序打断。这里改成进程内复用一条连接，并用 SerialUnavailable 明确
区分“串口不可用”，由上层决定如何降级。

设备名不再写死：树莓派 4 上通常就是 /dev/ttyAMA0，而树莓派 5 启用 UART 后
设备名可能是 /dev/ttyAMA0 或 /dev/serial0，具体取决于系统配置，所以这里按
候选列表逐个尝试，也支持用环境变量 PI_SERIAL_PORT 直接指定。

**串口静默模式**（`PI_SERIAL_DRYRUN=1`）：只打印将要下发的帧，不真正写串口。
用于下位机还没接上、或动作文件还没就位的排练阶段 —— 上层逻辑照常跑通，
只是动作不会真的执行。
"""
import os
import time
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from runtime_log import event

import serial

PORT_ENV = "PI_SERIAL_PORT"
BAUDRATE_ENV = "PI_SERIAL_BAUD"
DRYRUN_ENV = "PI_SERIAL_DRYRUN"

DEFAULT_BAUDRATE = 115200
PORT_CANDIDATES = ("/dev/ttyAMA0", "/dev/serial0", "/dev/ttyS0")

# 视为「开启」的取值
_TRUTHY = ("1", "true", "yes", "on")

# 下位机回传的应答帧，收到任一帧即认为本条指令执行完毕
ACK_FRAMES = (
    b'\xff\x00\x05\x05\x00\x00\x18"',
    b'\xff\x00\x05\x05\x00\x00\x19"',
)

IDLE_POLL = 0.05  # 空闲轮询间隔，避免空转占满 CPU

_serial = None


class SerialUnavailable(RuntimeError):
    """串口不可用，例如设备不存在、权限不足或已被占用。"""


def dry_run():
    """是否处于串口静默模式（只打印不发）。"""
    return os.getenv(DRYRUN_ENV, "").strip().lower() in _TRUTHY


def format_frame(data):
    """把数据帧格式化成便于阅读的十六进制串，例：ff 00 05 05 00 0c 09 ..."""
    return " ".join("%02x" % byte for byte in data)


class _SilentSerial:
    """串口静默模式下的替身：接口与 pyserial 保持一致，但不发送任何数据。

    供完整演出和独立动作排练使用。
    """

    def isOpen(self):
        return True

    def write(self, data):
        return len(data)

    def inWaiting(self):
        return 0

    def read(self, size=0):
        return b""

    def flushInput(self):
        pass

    def flush(self):
        pass

    def close(self):
        pass


_SILENT_SERIAL = _SilentSerial()


def candidate_ports():
    """待尝试的串口设备列表：PI_SERIAL_PORT 优先。"""
    override = os.getenv(PORT_ENV)
    if override:
        return (override,)
    return PORT_CANDIDATES


def default_baudrate():
    return int(os.getenv(BAUDRATE_ENV, str(DEFAULT_BAUDRATE)))


def open_serial(port, baudrate=DEFAULT_BAUDRATE):
    try:
        ser = serial.Serial(port, baudrate, timeout=0, write_timeout=2,
                            exclusive=True if os.name == 'posix' else None)
        if not ser.isOpen():
            ser.open()
        return ser
    except serial.SerialException as exc:
        raise SerialUnavailable("串口打开失败 %s@%s: %s" % (port, baudrate, exc)) from exc


def get_serial(port=None, baudrate=None):
    """取全局串口连接，必要时按候选列表逐个尝试建立连接。

    连接在进程内复用：机器人是长驻程序，反复开关串口既慢又容易撞上设备忙。
    串口静默模式下不打开任何设备，直接返回替身。
    """
    global _serial
    if _serial is not None and _serial.isOpen():
        return _serial

    if dry_run():
        _serial = _SILENT_SERIAL
        print("串口静默模式（%s=1）已开启：不会向下位机发送任何数据" % DRYRUN_ENV)
        return _serial

    baudrate = baudrate or default_baudrate()
    ports = (port,) if port else candidate_ports()

    errors = []
    for candidate in ports:
        try:
            _serial = open_serial(candidate, baudrate)
        except SerialUnavailable as exc:
            errors.append(str(exc))
            continue
        event('串口', '已连接 %s → %s @ %d，8N1' % (candidate, os.path.realpath(candidate), baudrate))
        return _serial

    raise SerialUnavailable(
        "没有可用的串口设备，已尝试:\n  %s\n"
        "请确认 raspi-config 中已启用 Serial Port（登录 shell 选 No、硬件串口选 Yes），"
        "或用 %s 指定设备名。\n"
        "如果只是想先跑通流程（不下发动作），可以设 %s=1 打开串口静默模式。" % (
            "\n  ".join(errors), PORT_ENV, DRYRUN_ENV)
    )


def close_serial():
    """关闭全局串口连接（退出程序或需要重新枚举设备时使用）。"""
    global _serial
    if _serial is not None:
        try:
            _serial.close()
        finally:
            _serial = None


def _trace(direction, data=b'', elapsed=None, detail=None):
    """保留收发原始证据；记录失败不影响指令处理。"""
    record = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'direction': direction, 'hex': format_frame(data)}
    if elapsed is not None:
        record['elapsed_seconds'] = round(elapsed, 6)
    if detail is not None:
        record['detail'] = detail
    try:
        path = Path(__file__).resolve().parent/'deployment_logs/serial-trace.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as output:
            output.write(json.dumps(record, ensure_ascii=False) + '\n')
    except OSError as exc:
        event('串口诊断', '无法保存原始记录：%s' % exc, debug=True)


def send_serial_data(ser, data, timeout=10.0):
    """发送一帧数据并等待下位机应答，返回是否收到应答。

    串口静默模式下只打印帧内容、立即返回成功（视为已下发）。
    """
    if dry_run():
        print("[串口静默] 跳过下发（%d 字节）：%s" % (len(data), format_frame(data)))
        return True

    # 只在本次发送前丢弃遗留回执；发送后不能清空缓冲区，否则会丢帧。
    stale_count = ser.inWaiting()
    if stale_count:
        stale = ser.read(min(stale_count, 4096))
        _trace('DISCARD_BEFORE_TX', stale, detail={'queued_bytes': stale_count})
        event('串口', '发送前清除 %d 字节遗留数据' % stale_count)
    reset = getattr(ser, 'reset_input_buffer', None) or ser.flushInput
    reset()
    event('串口', '发送动作指令；等待回执（最长 %.0f 秒）' % timeout)
    event('串口原始', 'TX ' + format_frame(data), debug=True)
    start_time = time.monotonic()
    written = ser.write(bytearray(data))
    _trace('TX', data, elapsed=0)
    if written != len(data):
        event('错误', '串口指令未完整写入：%s / %d 字节' % (written, len(data)))
        _trace('WRITE_FAILED', elapsed=time.monotonic()-start_time)
        return False
    pending = bytearray()
    received = 0
    tail_size = max(map(len, ACK_FRAMES)) - 1
    while time.monotonic() - start_time <= timeout:
        size = ser.inWaiting()
        if size:
            response = ser.read(min(size, 4096))
            received += len(response)
            event('串口原始', 'RX ' + format_frame(response), debug=True)
            if response:
                _trace('RX', response, elapsed=time.monotonic()-start_time)
                pending.extend(response)
                for frame in ACK_FRAMES:
                    if frame in pending:
                        elapsed = time.monotonic() - start_time
                        _trace('ACK', frame, elapsed=elapsed)
                        event('串口', '收到约定回执 %s | 等待 %.2f 秒' % (format_frame(frame), elapsed))
                        return True
                # 下次只需保留最长回执减一字节，既能重组分段帧，也限制内存。
                pending = pending[-tail_size:]
        time.sleep(IDLE_POLL)
    elapsed = time.monotonic() - start_time
    reason = '未收到任何返回数据' if not received else '收到 %d 字节，但未找到约定回执' % received
    event('错误', '串口等待回执超时 | 实际等待 %.2f 秒 | %s' % (elapsed, reason))
    _trace('TIMEOUT', pending, elapsed=elapsed, detail={'received_bytes': received})
    return False
