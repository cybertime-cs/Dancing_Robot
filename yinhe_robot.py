#!/usr/bin/env python3
"""银河号表演机器人主程序。

静默监听 -> Silero VAD -> sherpa-onnx 流式 ASR -> 指令匹配 -> 流程 FSM。
所有现场资源名称和可说的指令均在 speech_train.json 中维护。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from collections.abc import Callable, Iterable, Iterator
import json
import logging
import os
import select
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import serial
except ImportError:
    serial = None

try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None

try:
    from datapackage import DataPackageConverter
except ImportError:
    DataPackageConverter = None

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "speech_train.json"
EXEC_LOG = logging.getLogger("yinhe.execution")
LISTEN_LOG = logging.getLogger("yinhe.listener")


class MicrophoneUnavailable(RuntimeError):
    """当前系统尚未识别到可用的真实麦克风。"""


def configure_logging():
    """执行信息显示在主终端；监听信息独立写入文件供第二终端查看。"""
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    for logger in (EXEC_LOG, LISTEN_LOG):
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()

    execution_file = logging.FileHandler(log_dir / "execution.log", encoding="utf-8")
    execution_file.setFormatter(formatter)
    execution_console = logging.StreamHandler()
    execution_console.setFormatter(formatter)
    EXEC_LOG.addHandler(execution_file)
    EXEC_LOG.addHandler(execution_console)

    listener_file = logging.FileHandler(log_dir / "listener.log", encoding="utf-8")
    listener_file.setFormatter(formatter)
    LISTEN_LOG.addHandler(listener_file)


@contextmanager
def redirect_native_stderr(filename: Path):
    """将 ALSA/PortAudio 的 C 层诊断写入监听日志，避免污染执行终端。"""
    filename.parent.mkdir(exist_ok=True)
    saved_stderr = os.dup(2)
    target = os.open(str(filename), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o664)
    try:
        os.dup2(target, 2)
        yield
    finally:
        os.dup2(saved_stderr, 2)
        os.close(target)
        os.close(saved_stderr)


def initialize_serial():
    """严格保留原版 action_neo.py 的串口初始化逻辑。"""
    try:
        ser = serial.Serial('/dev/ttyUSB0', 115200)
        if not ser.isOpen():
            ser.open()
        return ser
    except serial.SerialException as exc:
        EXEC_LOG.error("串口初始化失败：%s", exc)
        print(f"Error:{exc}")
        raise Exception("Failed to initialize serial connection.")


def send_serial_data(ser, data):
    """严格保留原版 action_neo.py 的动作包发送及回包等待逻辑。"""
    ser.write(bytearray(data))
    start_time = time.time()
    timeout = 10
    buffer = b''

    while True:
        if time.time() - start_time > timeout:
            print("串口通信超时，自动退出循环")
            break

        size = ser.inWaiting()
        if size > 0:
            try:
                buffer += ser.read(size)
            except Exception as exc:
                print(f"Error:{exc}")
            if b'\xff\x00\x05\x05\x00\x00\x18' in buffer or b'\xff\x00\x05\x05\x00\x00\x19' in buffer:
                print("Sucess")
                print("Buffer:", buffer)
                ser.flushInput()
                break
            time.sleep(0.5)


@dataclass
class Hardware:
    """音频与串口动作执行器；串口仅在首次动作时打开。"""

    dry_run: bool = False
    _serial: Any = None

    def get_serial(self):
        if self.dry_run:
            return None
        if self._serial is None or not self._serial.is_open:
            if serial is None:
                raise RuntimeError("缺少 pyserial：请安装 requirements.txt")
            self._serial = initialize_serial()
            EXEC_LOG.info("串口初始化成功：/dev/ttyUSB0")
        return self._serial

    def close(self):
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def play_audio(self, filename: str, wait: bool = True, gain_db: float = 0) -> threading.Thread | None:
        """沿用原版 mplayer 播放方式，可为指定音频单独配置增益。"""
        gain_db = float(gain_db)
        path = ROOT / filename
        if not path.exists():
            EXEC_LOG.warning("音频文件不存在（请在配置中替换）：%s", path)
            return None
        if self.dry_run:
            EXEC_LOG.info("[演练] 播放音频：%s；增益：%+g dB", filename, gain_db)
            return None

        def run():
            EXEC_LOG.info("开始播放音频：%s", filename)
            if gain_db:
                EXEC_LOG.info("本段音频独立增益：%+g dB", gain_db)
            try:
                if gain_db:
                    status = os.system('mplayer -volume 100 -af volume=%g %s' % (gain_db, filename))
                else:
                    status = os.system('mplayer -volume 100 %s' % filename)
                if status != 0:
                    EXEC_LOG.error("音频播放命令失败（状态 %s）：%s", status, filename)
                else:
                    EXEC_LOG.info("音频播放结束：%s", filename)
            except OSError as exc:
                EXEC_LOG.error("无法播放 %s：%s", filename, exc)

        if wait:
            run()
            return None
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

    def send_action(self, filename: str):
        """发送主控板内置动作文件名；树莓派不保存、不读取动作文件。"""
        if self.dry_run:
            EXEC_LOG.info("[演练] 发送动作：%s", filename)
            return
        if DataPackageConverter is None:
            raise RuntimeError("找不到 datapackage.DataPackageConverter，请复制机器人 SDK 到本目录/PYTHONPATH")
        try:
            EXEC_LOG.info("准备发送主控动作文件：%s", filename)
            movements = DataPackageConverter(filename).hex_output
            ser = self.get_serial()
            EXEC_LOG.info("动作包已写入串口，等待主控回包：%s", filename)
            send_serial_data(ser, movements)
            EXEC_LOG.info("主控动作流程已返回：%s", filename)
            return True
        except Exception as exc:
            # 树莓派单机演练时没有串口也要完整播放剧情；现场接上主控后会正常发送。
            EXEC_LOG.error("动作包未发送：%s；跳过动作并继续后续音频。原因：%s", filename, exc)
            self.close()
            return False


class CommandParser:
    def __init__(self, config: dict[str, Any]):
        self.commands = config["commands"]

    @staticmethod
    def clean(text: str) -> str:
        return "".join(text.lower().split()).translate(str.maketrans("", "", "，。！,.!"))

    def match(self, text: str) -> tuple[str | None, dict[str, Any] | None]:
        normalized = self.clean(text)
        candidates: list[tuple[tuple[bool, int], str, dict[str, Any]]] = []
        for command_id, command in self.commands.items():
            for phrase in command["phrases"]:
                phrase = self.clean(phrase)
                if phrase and phrase in normalized:
                    # 完全匹配优先；其余情况仍采用包含式匹配，例如“出发”。
                    candidates.append(((normalized == phrase, len(phrase)), command_id, command))
        if not candidates:
            return None, None
        best_score = max(item[0] for item in candidates)
        best = [item for item in candidates if item[0] == best_score]
        # 同一强度的短口令对应多个流程时，不执行任何流程以避免误触发。
        if len({item[1] for item in best}) > 1:
            EXEC_LOG.warning("指令匹配冲突：%s", text)
            return None, None
        _, command_id, command = best[0]
        return command_id, command


def matches_master_wake(config: dict[str, Any], text: str) -> bool:
    """主唤醒必须包含完整口令，只忽略空格和常见标点。"""
    normalized = CommandParser.clean(text)
    return any(
        phrase and phrase in normalized
        for phrase in (
            CommandParser.clean(item)
            for item in config.get("master_wake", {}).get("phrases", [])
        )
    )


class PerformanceFSM:
    WAITING_FOR_MASTER_WAKE = "WAITING_FOR_MASTER_WAKE"
    IDLE = "IDLE"
    EXECUTING = "EXECUTING"

    def __init__(self, config: dict[str, Any], hardware: Hardware):
        self.config = config
        self.parser = CommandParser(config)
        self.hardware = hardware
        self.state = self.WAITING_FOR_MASTER_WAKE

    def accepts_text(self, text: str) -> bool:
        """只检查当前状态允许的口令，不执行流程，供实时 ASR 使用。"""
        if self.state == self.WAITING_FOR_MASTER_WAKE:
            return matches_master_wake(self.config, text)
        if self.state == self.IDLE:
            return self.parser.match(text)[1] is not None
        return False

    def handle_text(self, text: str) -> bool:
        if self.state == self.WAITING_FOR_MASTER_WAKE:
            if matches_master_wake(self.config, text):
                self.state = self.IDLE
                EXEC_LOG.info("主唤醒词已识别，开始播放就位音频。")
                self.run("master_wake", self.config["master_wake"])
                EXEC_LOG.info("主唤醒播报完成，银河号已解锁，开始响应原有口令。")
                LISTEN_LOG.info("主唤醒成功，进入已解锁的静默监听。")
                # 播完主唤醒音频后再监听下一句；本句中的其他剧情口令不执行。
                return True
            LISTEN_LOG.info("等待主唤醒，忽略本次识别结果：%s", text)
            return False
        command_id, command = self.parser.match(text)
        if command is None:
            EXEC_LOG.info("未匹配指令：%s", text)
            return False
        EXEC_LOG.info("识别指令：%s -> %s", text, command_id)
        self.run(command_id, command)
        return True

    def run(self, command_id: str, command: dict[str, Any]):
        if self.state != self.IDLE:
            EXEC_LOG.warning("机器人忙碌中，忽略：%s", command_id)
            return
        self.state = self.EXECUTING
        completed = False
        try:
            for step in command.get("steps", []):
                self._run_step(step)
            completed = True
        except Exception:
            EXEC_LOG.exception("流程 %s 执行失败", command_id)
        finally:
            if completed and command.get("return_to_master_wake", False):
                self.state = self.WAITING_FOR_MASTER_WAKE
                EXEC_LOG.info("最后流程 %s 完成，银河号已重新锁定，等待主唤醒。", command_id)
                LISTEN_LOG.info("本轮表演结束，只响应主唤醒词，其他剧情口令已屏蔽。")
            else:
                self.state = self.IDLE
                EXEC_LOG.info("流程 %s 已结束，回到静默监听", command_id)

    def _run_step(self, step: dict[str, Any]):
        kind = step["type"]
        EXEC_LOG.info("开始步骤：%s", kind)
        if kind == "audio":
            self.hardware.play_audio(step["file"], wait=True, gain_db=step.get("gain_db", 0))
        elif kind == "action":
            self.hardware.send_action(step["file"])
        elif kind == "show":
            # 音乐与动作同时开始；动作时长结束后再进入下一剧情。
            music = self.hardware.play_audio(step["music"], wait=False) if step.get("music") else None
            self.hardware.send_action(step["action"])
            if music:
                music.join()
                EXEC_LOG.info("动作音乐已结束：%s", step["music"])
            if step.get("after_audio"):
                EXEC_LOG.info("播放动作后的语音：%s", step["after_audio"])
                self.hardware.play_audio(step["after_audio"], wait=True)
        elif kind == "wait":
            time.sleep(float(step["seconds"]))
        elif kind == "note":
            EXEC_LOG.info("现场功能提示：%s", step["text"])
        else:
            raise ValueError(f"未知步骤类型：{kind}")


class SherpaStreamingRecognizer:
    """Silero VAD 实时语音段 + Sherpa 增量解码，支持口令提前触发。"""

    def __init__(self, asr_config: dict[str, Any]):
        if sherpa_onnx is None:
            raise RuntimeError("缺少 sherpa-onnx：请安装 requirements.txt")
        model_dir = ROOT / asr_config["model_dir"]
        self.sample_rate = int(asr_config.get("sample_rate", 16000))
        self.alsa_device = asr_config.get("alsa_device", "pulse")
        self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(model_dir / asr_config["tokens"]),
            encoder=str(model_dir / asr_config["encoder"]),
            decoder=str(model_dir / asr_config["decoder"]),
            joiner=str(model_dir / asr_config["joiner"]),
            num_threads=int(asr_config.get("num_threads", 2)),
            sample_rate=self.sample_rate,
            feature_dim=80,
            decoding_method="greedy_search",
        )
        vad_model = ROOT / asr_config["vad_model"]
        # 采用官方 Python 示例的逐项配置写法，兼容当前 sherpa-onnx 绑定。
        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = str(vad_model)
        vad_config.silero_vad.threshold = float(asr_config.get("vad_threshold", 0.25))
        vad_config.silero_vad.min_silence_duration = float(asr_config.get("vad_min_silence", 0.5))
        vad_config.silero_vad.min_speech_duration = float(asr_config.get("vad_min_speech", 0.3))
        vad_config.silero_vad.max_speech_duration = float(asr_config.get("vad_max_speech", 10))
        vad_config.sample_rate = self.sample_rate
        vad_config.num_threads = int(asr_config.get("num_threads", 2))
        self.vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)

    def _audio_chunks(self, max_seconds: float | None) -> Iterator[Any]:
        """持续读取同一个 ALSA 录音进程；结束监听时释放麦克风。"""
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("缺少 numpy：请安装 requirements.txt") from exc

        started = time.monotonic()
        last_audio = started
        native_log = ROOT / "logs" / "listener-alsa.log"
        native_log.parent.mkdir(exist_ok=True)
        recorder = None
        error_file = None
        try:
            error_file = native_log.open("ab", buffering=0)
            command = [
                "arecord", "-q", "-D", self.alsa_device,
                "-f", "S16_LE", "-c", "1", "-r", str(self.sample_rate),
                "-t", "raw",
            ]
            try:
                recorder = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error_file)
            except (FileNotFoundError, OSError) as exc:
                error_file.close()
                raise MicrophoneUnavailable(f"无法启动 ALSA 录音：{exc}") from exc

            LISTEN_LOG.info("使用 ALSA 录音设备：%s（%d Hz，单声道）", self.alsa_device, self.sample_rate)
            frames_per_buffer = 512
            bytes_per_buffer = frames_per_buffer * 2
            pending_bytes = b""
            while max_seconds is None or time.monotonic() - started < max_seconds:
                if recorder.stdout is None:
                    raise MicrophoneUnavailable("ALSA 录音没有返回音频管道")
                ready, _, _ = select.select([recorder.stdout], [], [], 0.1)
                if not ready:
                    if recorder.poll() is not None:
                        raise MicrophoneUnavailable(
                            f"ALSA 无法打开录音设备 {self.alsa_device}，详情见 logs/listener-alsa.log"
                        )
                    if time.monotonic() - last_audio > 5:
                        raise MicrophoneUnavailable(
                            f"ALSA 录音设备 {self.alsa_device} 连续 5 秒未返回数据，详情见 logs/listener-alsa.log"
                        )
                    continue
                # 不使用 BufferedReader.read(n)，避免等待凑满指定长度。
                raw_audio = os.read(recorder.stdout.fileno(), bytes_per_buffer)
                if not raw_audio:
                    raise MicrophoneUnavailable(
                        f"ALSA 录音设备 {self.alsa_device} 未返回音频，详情见 logs/listener-alsa.log"
                    )
                last_audio = time.monotonic()
                raw_audio = pending_bytes + raw_audio
                complete_bytes = len(raw_audio) // 2 * 2
                pending_bytes = raw_audio[complete_bytes:]
                if complete_bytes:
                    yield np.frombuffer(raw_audio[:complete_bytes], dtype=np.int16).astype(np.float32) / 32768.0
        finally:
            if recorder is not None:
                if recorder.stdout is not None:
                    recorder.stdout.close()
                if recorder.poll() is None:
                    recorder.terminate()
                    try:
                        recorder.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        recorder.kill()
                        recorder.wait()
            if error_file is not None:
                error_file.close()

    def _transcripts(self, chunks: Iterable[Any]) -> Iterator[tuple[str, bool]]:
        """语音尚未结束就增量解码；每个样本只送入 ASR 一次。"""
        import numpy as np

        stream = None
        segment_start = None
        samples_sent = 0
        last_text = ""
        pending = np.empty(0, dtype=np.float32)
        self.vad.reset()

        def decode_segment(segment, final=False):
            nonlocal stream, segment_start, samples_sent, last_text
            if stream is None or segment_start != segment.start:
                stream = self.recognizer.create_stream()
                segment_start = segment.start
                samples_sent = 0
                last_text = ""
            samples = segment.samples
            if len(samples) > samples_sent:
                stream.accept_waveform(self.sample_rate, samples[samples_sent:])
                samples_sent = len(samples)
            if final:
                # 句尾补静音只用于收尾，不影响此前的实时口令触发。
                stream.accept_waveform(self.sample_rate, np.zeros(int(0.3 * self.sample_rate), dtype=np.float32))
                stream.input_finished()
            while self.recognizer.is_ready(stream):
                self.recognizer.decode_stream(stream)
                text = self.recognizer.get_result(stream)
                text = (text if isinstance(text, str) else text.text).strip()
                if text and text != last_text:
                    last_text = text
                    LISTEN_LOG.info("ASR 实时结果：%s", text)
                    yield text, False
            if final:
                yield last_text, True
                stream = None
                segment_start = None
                samples_sent = 0
                last_text = ""

        def process_frame(frame):
            self.vad.accept_waveform(frame)
            while not self.vad.empty():
                yield from decode_segment(self.vad.front, final=True)
                self.vad.pop()
            if self.vad.is_speech_detected():
                # current_segment 包含 VAD 判断起音前的回溯样本，不丢口令开头。
                yield from decode_segment(self.vad.current_segment)

        try:
            for samples in chunks:
                pending = np.concatenate((pending, samples))
                while len(pending) >= 512:
                    yield from process_frame(pending[:512])
                    pending = pending[512:]
            if len(pending):
                yield from process_frame(np.pad(pending, (0, 512 - len(pending))))
            self.vad.flush()
            while not self.vad.empty():
                yield from decode_segment(self.vad.front, final=True)
                self.vad.pop()
        finally:
            # 提前触发或录音异常后，不能把上一句残留语音带到下一次监听。
            self.vad.reset()

    def listen_once(
        self,
        max_seconds: float | None = 7,
        match_partial: Callable[[str], bool] | None = None,
    ) -> str:
        """主程序命中口令就返回；训练程序不传匹配器，仍返回完整识别句。"""
        chunks = self._audio_chunks(max_seconds)
        transcripts = self._transcripts(chunks)
        try:
            for text, final in transcripts:
                if not text:
                    continue
                if match_partial is not None:
                    if match_partial(text):
                        LISTEN_LOG.info("实时口令命中，停止录音并执行：%s", text)
                        return text
                    if final:
                        LISTEN_LOG.info("整句未命中当前可用口令，继续监听：%s", text)
                elif final:
                    return text
            return ""
        finally:
            transcripts.close()
            chunks.close()


def load_config() -> dict[str, Any]:
    with CONFIG_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def main() -> int:
    cli = argparse.ArgumentParser(description="银河号表演机器人")
    cli.add_argument("--dry-run", action="store_true", help="不播放、不发送串口包，只打印流程")
    cli.add_argument("--text", action="append", help="绕过麦克风，按顺序处理文本；可重复传入以联调主唤醒和剧情口令")
    args = cli.parse_args()
    config = load_config()
    hardware = Hardware(dry_run=args.dry_run, **config.get("hardware", {}))
    fsm = PerformanceFSM(config, hardware)
    try:
        if args.text:
            handled = False
            for text in args.text:
                handled = fsm.handle_text(text) or handled
            return 0 if handled else 2
        recognizer = SherpaStreamingRecognizer(config["asr"])
        EXEC_LOG.info("机器人初始化完成，播放监听就绪提示音。")
        hardware.play_audio("resources/audio/ding.wav", wait=True)
        master_phrases = config["master_wake"]["phrases"]
        EXEC_LOG.info("银河号等待主唤醒：%s", master_phrases[0])
        LISTEN_LOG.info("银河号已开机，持续监听主唤醒词：%s；按 Ctrl+C 退出。", " / ".join(master_phrases))
        while True:
            LISTEN_LOG.info("等待语音输入……")
            try:
                text = recognizer.listen_once(max_seconds=None, match_partial=fsm.accepts_text)
            except MicrophoneUnavailable as exc:
                LISTEN_LOG.warning("%s；2 秒后重试。", exc)
                time.sleep(2)
                continue
            if text:
                LISTEN_LOG.info("ASR 识别结果：%s", text)
                fsm.handle_text(text)
            else:
                LISTEN_LOG.info("本次监听未识别到有效语音。")
    except KeyboardInterrupt:
        LISTEN_LOG.info("已停止")
    except Exception as exc:
        # 错误只记录在监听日志，避免执行终端被 traceback 刷屏。
        LISTEN_LOG.error("监听异常，主程序停止：%s", exc)
        return 1
    finally:
        hardware.close()
    return 0


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(main())
