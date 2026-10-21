import json
import math
import shutil
import subprocess
import time
import wave
from pathlib import Path

import pyaudio
import vosk


# ============================================================
# 路径配置
# ============================================================

# 当前 speech_recog.py 所在目录
BASE_DIR = Path(__file__).resolve().parent

MODEL_DIR = BASE_DIR / "model"
RESOURCE_DIR = BASE_DIR / "resources"
TEMP_RECORD_DIR = BASE_DIR / "temp_record"

DING_FILE = RESOURCE_DIR / "ding.wav"
DONG_FILE = RESOURCE_DIR / "dong.wav"
TEMP_WAV_FILE = TEMP_RECORD_DIR / "temp.wav"
RESULT_FILE = BASE_DIR / "result.txt"
SPEECH_LOG_FILE = BASE_DIR / "speech.txt"


# ============================================================
# 录音参数
# ============================================================

FRAME_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2

# 树莓派上适当增大缓冲区，可以降低 Input overflowed 的概率
CHUNK_SIZE = 4096


# ============================================================
# 初始化 Vosk
# ============================================================

vosk.SetLogLevel(-1)

if not MODEL_DIR.exists():
    raise FileNotFoundError(f"找不到 Vosk 模型目录：{MODEL_DIR}")

model = vosk.Model(str(MODEL_DIR))


# ============================================================
# 播放提示音
# ============================================================

def play_sound(sound_file):
    """同步播放提示音，播放结束后立即返回。"""
    if not sound_file.exists():
        print(f"提示音文件不存在：{sound_file}")
        return

    subprocess.run(
        [
            "mplayer",
            "-really-quiet",
            str(sound_file),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )



# ============================================================
# 保存 WAV 文件
# ============================================================

def save_wave_file(filename: Path, audio_frames: list[bytes]):
    """
    将录音数据保存成单声道、16kHz、16bit PCM WAV 文件。
    """
    filename.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(FRAME_RATE)
        wf.writeframes(b"".join(audio_frames))


# ============================================================
# 录音
# ============================================================

def record(filename, duration=3):
    """
    提前创建麦克风流，但暂不启动。
    ding 播放结束后立即开始录音。
    """
    if duration <= 0:
        raise ValueError("录音时间必须大于 0")

    audio = pyaudio.PyAudio()
    stream = None
    audio_frames = []

    try:
        # 提前初始化麦克风，避免 ding 后再初始化产生延迟
        # start=False 表示此时不采集音频，因此不会缓冲溢出
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=FRAME_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
            start=False,
        )

        # 播放提示音，此时麦克风流尚未启动
        play_sound(DING_FILE)

        # ding 结束后立即启动录音，不需要 sleep
        stream.start_stream()

        print("开始录音")
        print(f"录音中（{duration} 秒）")

        read_count = math.ceil(
            FRAME_RATE * duration / CHUNK_SIZE
        )

        for _ in range(read_count):
            data = stream.read(
                CHUNK_SIZE,
                exception_on_overflow=False,
            )

            audio_frames.append(data)
            print(".", end="", flush=True)

        print("\n录音结束")

    except OSError as exc:
        raise RuntimeError(
            f"麦克风录音失败：{exc}"
        ) from exc

    finally:
        if stream is not None:
            try:
                if stream.is_active():
                    stream.stop_stream()
            finally:
                stream.close()

        audio.terminate()

    if not audio_frames:
        raise RuntimeError("没有录制到音频数据")

    save_wave_file(filename, audio_frames)

    # 麦克风关闭后播放结束提示音
    play_sound(DONG_FILE)


# ============================================================
# 语音识别
# ============================================================

def speech_recog() -> str:
    """
    录音并使用 Vosk 进行离线语音识别。

    返回：
        去除空格后的识别文本。
    """
    TEMP_RECORD_DIR.mkdir(parents=True, exist_ok=True)

    record(
        TEMP_WAV_FILE,
        duration=3,
    )

    recognized_parts: list[str] = []

    # 每次识别都创建新的 Recognizer，
    # 避免上一次识别状态影响下一次
    recognizer = vosk.KaldiRecognizer(
        model,
        FRAME_RATE,
    )

    recognizer.SetWords(True)
    recognizer.SetPartialWords(True)

    with wave.open(str(TEMP_WAV_FILE), "rb") as wf:
        if wf.getnchannels() != CHANNELS:
            raise ValueError(
                f"WAV 必须是单声道，当前声道数：{wf.getnchannels()}"
            )

        if wf.getsampwidth() != SAMPLE_WIDTH:
            raise ValueError(
                f"WAV 必须是 16bit，当前采样宽度：{wf.getsampwidth()}"
            )

        if wf.getframerate() != FRAME_RATE:
            raise ValueError(
                f"WAV 必须是 {FRAME_RATE}Hz，"
                f"当前采样率：{wf.getframerate()}Hz"
            )

        if wf.getcomptype() != "NONE":
            raise ValueError("WAV 必须是未压缩的 PCM 格式")

        while True:
            data = wf.readframes(4000)

            if not data:
                break

            if recognizer.AcceptWaveform(data):
                result = json.loads(
                    recognizer.Result()
                )

                text = result.get("text", "").strip()

                if text:
                    recognized_parts.append(text)

        # 获取最后一段尚未输出的识别结果
        final_result = json.loads(
            recognizer.FinalResult()
        )

        final_text = final_result.get("text", "").strip()

        if final_text:
            recognized_parts.append(final_text)

    # 合并各段结果
    recognized_text = "".join(recognized_parts)

    # 保持原代码行为：删除英文单词之间的空格
    recognized_text = recognized_text.replace(" ", "")

    RESULT_FILE.write_text(
        recognized_text,
        encoding="utf-8",
    )

    return recognized_text


# ============================================================
# 单独运行 speech_recog.py 时的测试代码
# ============================================================

if __name__ == "__main__":
    try:
        text = speech_recog()

        print(f"识别结果：{text or '未识别到内容'}")

        if text:
            with SPEECH_LOG_FILE.open(
                "a",
                encoding="utf-8",
            ) as log_file:
                log_file.write(text + "\n")

    except KeyboardInterrupt:
        print("\n用户终止程序")

    except Exception as exc:
        print(f"语音识别失败：{exc}")