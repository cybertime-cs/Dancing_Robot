#!/usr/bin/env python3
"""通过 Hiwonder WonderEcho I2C 协议读取模块的离线识别结果。

模块是 I2C 从机：默认地址 0x34（新版也可能为 0x33），识别结果位于
0x64 寄存器，读取长度为 1 字节。0 表示当前没有新识别结果，非 0 值
是模块固件中为命令词配置的 ID。
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Iterator

try:
    import smbus2 as smbus
except ImportError:
    try:
        import smbus  # type: ignore[no-redef]
    except ImportError as exc:
        raise SystemExit("缺少 smbus2：请执行 .venv/bin/pip install smbus2") from exc

from yinhe_robot import (
    EXEC_LOG,
    LISTEN_LOG,
    Hardware,
    PerformanceFSM,
    configure_logging,
    load_config,
)


ROOT = Path(__file__).resolve().parent
MODULE_CONFIG_FILE = ROOT / "hiwonder_module.json"
MODULE_LOG = logging.getLogger("yinhe.module")


def configure_module_logging() -> None:
    configure_logging()
    MODULE_LOG.setLevel(logging.INFO)
    MODULE_LOG.propagate = False
    MODULE_LOG.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logfile = logging.FileHandler(ROOT / "logs" / "module.log", encoding="utf-8")
    logfile.setFormatter(formatter)
    MODULE_LOG.addHandler(console)
    MODULE_LOG.addHandler(logfile)


def parse_number(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return int(value, 0)


class HiwonderModule:
    """按官方 WonderEcho 协议轮询模块识别结果。"""

    def __init__(
        self,
        bus_number: int = 1,
        addresses: tuple[int, ...] = (0x34, 0x33),
        result_register: int = 0x64,
        poll_interval: float = 0.05,
    ):
        self.bus_number = bus_number
        self.addresses = addresses
        self.result_register = result_register
        self.poll_interval = poll_interval
        try:
            self.bus = smbus.SMBus(bus_number)
        except OSError as exc:
            raise RuntimeError(
                f"无法打开 /dev/i2c-{bus_number}。请先启用树莓派 I2C，并用模块的 "
                "SDA/SCL/GND 引脚连接树莓派。"
            ) from exc
        self.address = self._detect_address()

    def _detect_address(self) -> int:
        errors = []
        for address in self.addresses:
            try:
                # 返回 0 也表示通信成功，只是当前没有识别结果。
                self.bus.read_i2c_block_data(address, self.result_register, 1)
                MODULE_LOG.info("已连接模块：I2C-%d 地址 0x%02X", self.bus_number, address)
                return address
            except OSError as exc:
                errors.append(f"0x{address:02X}: {exc}")
        self.bus.close()
        raise RuntimeError(
            "I2C 总线上未发现模块（尝试地址："
            + ", ".join(f"0x{x:02X}" for x in self.addresses)
            + "）。请检查 SDA、SCL、GND、供电和 I2C 开关。详情："
            + "; ".join(errors)
        )

    def read_recognition_id(self) -> int:
        data = self.bus.read_i2c_block_data(self.address, self.result_register, 1)
        return int(data[0]) if data else 0

    def recognition_events(self) -> Iterator[int]:
        """只在 0 -> 非 0 或 ID 变化时产生事件，避免一次识别被重复执行。"""
        last_id = 0
        while True:
            try:
                result_id = self.read_recognition_id()
            except OSError as exc:
                MODULE_LOG.warning("模块读取失败，稍后重试：%s", exc)
                time.sleep(0.5)
                continue
            if result_id == 0:
                last_id = 0
            elif result_id != last_id:
                last_id = result_id
                yield result_id
            time.sleep(self.poll_interval)

    def close(self) -> None:
        self.bus.close()


def load_module_config() -> dict[str, Any]:
    with MODULE_CONFIG_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def main() -> int:
    parser = argparse.ArgumentParser(description="银河号 Hiwonder 模块识别结果读取器")
    parser.add_argument("--run-flows", action="store_true", help="按映射表执行银河号流程")
    parser.add_argument("--dry-run", action="store_true", help="执行流程时不播放音频、不发送动作")
    parser.add_argument("--once", action="store_true", help="读取到一个非零识别 ID 后退出")
    args = parser.parse_args()

    configure_module_logging()
    module_config = load_module_config()
    addresses = tuple(parse_number(value) for value in module_config.get("i2c_addresses", ["0x34", "0x33"]))
    try:
        module = HiwonderModule(
            bus_number=int(module_config.get("i2c_bus", 1)),
            addresses=addresses,
            result_register=parse_number(module_config.get("result_register", "0x64")),
            poll_interval=float(module_config.get("poll_interval", 0.05)),
        )
    except RuntimeError as exc:
        MODULE_LOG.error("模块初始化失败：%s", exc)
        return 1
    hardware = None
    try:
        fsm = None
        command_ids = {int(key): value for key, value in module_config.get("command_ids", {}).items()}
        if args.run_flows:
            config = load_config()
            hardware = Hardware(dry_run=args.dry_run, **config.get("hardware", {}))
            fsm = PerformanceFSM(config, hardware)
            EXEC_LOG.info("模块输入流程初始化完成，播放监听就绪提示音。")
            hardware.play_audio("resources/audio/ding.wav", wait=True)
        MODULE_LOG.info("等待模块识别结果……按 Ctrl+C 退出。")
        for result_id in module.recognition_events():
            command_id = command_ids.get(result_id)
            MODULE_LOG.info(
                "模块识别 ID：%d (0x%02X)%s",
                result_id,
                result_id,
                f" -> {command_id}" if command_id else "（尚未绑定流程）",
            )
            if fsm is not None and command_id:
                command = fsm.config.get("commands", {}).get(command_id)
                if command is None:
                    MODULE_LOG.error("映射的流程不存在：%s", command_id)
                else:
                    fsm.run(command_id, command)
            if args.once:
                break
    except KeyboardInterrupt:
        MODULE_LOG.info("已停止")
    finally:
        module.close()
        if hardware is not None:
            hardware.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
