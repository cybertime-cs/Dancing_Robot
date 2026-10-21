import math
import wave
from pathlib import Path
import pyaudio

# ============================================================
# 路径与录音参数配置（沿用你的原有配置）
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
TEMP_RECORD_DIR = BASE_DIR / "temp_record"
TEMP_WAV_FILE = TEMP_RECORD_DIR / "temp.wav"

FRAME_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
CHUNK_SIZE = 4096


# ============================================================
# 保存 WAV 文件
# ============================================================
def save_wave_file(filename: Path, audio_frames: list[bytes]):
    """将录音数据保存成单声道、16kHz、16bit PCM WAV 文件。"""
    filename.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(FRAME_RATE)
        wf.writeframes(b"".join(audio_frames))


# ============================================================
# 录音 3 秒核心函数
# ============================================================
def record_3_seconds(filename=TEMP_WAV_FILE, duration=3):
    """
    录音指定时长（默认3秒），并保存为 WAV 文件。
    """
    if duration <= 0:
        raise ValueError("录音时间必须大于 0")

    audio = pyaudio.PyAudio()
    stream = None
    audio_frames = []

    try:
        # 初始化麦克风流
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=FRAME_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )

        print(f"开始录音（{duration} 秒）...")
        
        # 计算需要读取的块数
        read_count = math.ceil(FRAME_RATE * duration / CHUNK_SIZE)

        for _ in range(read_count):
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            audio_frames.append(data)
            print(".", end="", flush=True)

        print("\n录音结束")

    except OSError as exc:
        raise RuntimeError(f"麦克风录音失败：{exc}") from exc

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
    print(f"音频已保存至：{filename}")


# ============================================================
# 测试运行
# ============================================================
if __name__ == "__main__":
    try:
        record_3_seconds()  # 默认录音 3 秒
    except KeyboardInterrupt:
        print("\n用户终止程序")
    except Exception as exc:
        print(f"录音失败：{exc}")