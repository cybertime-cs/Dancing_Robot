# audio.py
"""音频播放、录音与**麦克风打开方式**的统一封装。

播放优先用 mplayer（本项目一贯用法），缺失时回退 ffplay；
录音对外统一为 16kHz / 单声道 / 16bit PCM，与 sherpa-onnx 的输入要求一致。

为什么要有 `open_input_stream()`（2026-09-30 真机踩到）：
    不少 USB 麦克风/声卡**只支持 44100 或 48000 Hz**，对它直接 `rate=16000` 开流会被
    ALSA 拒掉，PyAudio 抛

        OSError: [Errno -9997] Invalid sample rate

    而报错只指向 pyaudio 内部（外加一屏 JACK/ALSA 噪音），完全看不出是"这台麦克风
    不支持 16kHz"。整理前 wake.py / audio.py 各自硬编码 16000，于是同一个坑埋了两处。

现在的做法：**先试 16kHz，不行就问设备支持多少，再在软件里重采样回 16kHz**。
上层（唤醒 / 识别）拿到的永远是 16kHz，不需要知道底下是什么设备。
设备本来就支持 16kHz 时不会多做一次重采样，行为与整理前完全一致。

想固定用某个麦克风：`MIC_DEVICE=<索引>`（运行 scripts/pi_audio_setup.sh 查看 PyAudio 设备索引）。
"""
import collections
import os
import shutil
import wave
import tempfile
import time
from runtime_log import event

from paths import find_audio

FRAMERATE = 16000  # 对外统一的采样率：所有语音模型的输入要求
CHANNELS = 1
SAMPWIDTH = 2
CHUNK = 2000

MIC_DEVICE_ENV = "MIC_DEVICE"

# 依次尝试的采样率。目标采样率排第一 —— 设备支持 16k 时首选它，
# 所以正常环境不会因为这套机制而改变行为。
FALLBACK_RATES = (16000, 48000, 44100, 32000, 22050, 8000)

# open_input_stream() 的返回值：
#   rate              实际打开成功的采样率
#   frames_per_buffer 换算到该采样率后的块大小（时长与在目标采样率下一致）
MicStream = collections.namedtuple("MicStream", "stream rate frames_per_buffer")


# --------------------------------------------------------------------------
# ALSA 噪声抑制（架构无关；加载不到 libasound 时静默跳过）
#
# ALSA 在探测设备时会在 stderr 上打一屏无关紧要的错（"jack server is not running"、
# "Cannot connect to server socket" 等），既吓人又淹没真正的报错，这里整体压掉。
# --------------------------------------------------------------------------
from contextlib import contextmanager  # noqa: E402
from ctypes import CFUNCTYPE, c_char_p, c_int, cdll  # noqa: E402


@contextmanager
def _device_diagnostics():
    """仅设备探测期间收集底层 stderr；异常照常上抛，完整信息保留在文件。"""
    if os.name != 'posix' or os.getenv('ROBOT_DEBUG', '') == '1':
        yield
        return
    saved = os.dup(2)
    with tempfile.TemporaryFile() as capture:
        try:
            os.dup2(capture.fileno(), 2)
            yield
        finally:
            os.dup2(saved, 2)
            os.close(saved)
            capture.seek(0)
            diagnostic = capture.read()
            if diagnostic:
                from paths import ensure_temp_record_dir
                with open(os.path.join(ensure_temp_record_dir(), 'audio-driver.log'), 'ab') as output:
                    output.write(diagnostic)


@contextmanager
def no_alsa_error():
    """临时换掉 ALSA 的错误处理器，压掉设备探测时打在 stderr 的一屏噪音。

    **这里只能有一次 yield。** 写成「try: yield / except: yield」的话，异常被抛进
    第一个 yield 时会被那个宽泛的 except 抓住、再 yield 一次，于是 contextlib 报

        RuntimeError: generator didn't stop after throw()

    **真正的错误（ALSA / PortAudio 的）就被这条毫无意义的报错盖掉了** ——
    2026-09-30 真机上就是这么撞的：本该看到 "Invalid sample rate"，看到的却是这个。
    所以「libasound 能不能加载」必须在 yield **之前**判定，加载不到就不做抑制，
    但同样只 yield 一次（异常因此能原样穿出去）。
    """
    asound = None
    # 保留引用：回调对象被 GC 掉而 ALSA 仍持有它的话，会调用到已释放的函数指针
    handler = None
    try:
        asound = cdll.LoadLibrary("libasound.so")
        handler = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)(lambda *a: None)
        asound.snd_lib_error_set_handler(handler)
    except Exception:  # noqa: BLE001 —— 没有 libasound 也能跑，只是噪音多些
        asound = None

    try:
        with _device_diagnostics():
            yield
    finally:
        if asound is not None:
            try:
                asound.snd_lib_error_set_handler(None)
            except Exception:  # noqa: BLE001
                pass
        del handler


# --------------------------------------------------------------------------
# 麦克风：设备选择 + 采样率协商 + 重采样
# --------------------------------------------------------------------------
def _input_device_index(pyaudio_instance):
    """选要用的录音设备索引：MIC_DEVICE > 系统默认 > 第一个有输入通道的设备。

    参数是 `pyaudio.PyAudio()` 的**实例**（设备查询是实例方法，不是模块函数）。
    找不到任何能录音的设备时返回 None（由调用方给出可执行的排查提示）。
    """
    device_name = os.getenv('MIC_DEVICE_NAME', '').strip()
    if device_name:
        for index in range(pyaudio_instance.get_device_count()):
            info = pyaudio_instance.get_device_info_by_index(index)
            if device_name.casefold() in str(info.get('name', '')).casefold() and int(info.get('maxInputChannels') or 0) > 0:
                event('设备', '%s（索引 %d）' % (info['name'], index), debug=True)
                return index
        raise RuntimeError('未找到指定麦克风：%s；请检查连接或 MIC_DEVICE_NAME 配置' % device_name)
    override = os.getenv(MIC_DEVICE_ENV, "").strip()
    if override:
        try:
            return int(override)
        except ValueError:
            print("[audio] %s=%r 不是数字，已忽略" % (MIC_DEVICE_ENV, override))

    try:
        return int(pyaudio_instance.get_default_input_device_info()["index"])
    except Exception:  # noqa: BLE001
        pass

    # 系统没给出默认输入设备：自己扫一遍，挑第一个带输入通道的。
    # 树莓派 5 本身没有模拟输入，只插了输出设备时「默认设备」会指向播放端，
    # 对它开录音流必然失败 —— 所以这一步是必要的。
    try:
        for index in range(pyaudio_instance.get_device_count()):
            info = pyaudio_instance.get_device_info_by_index(index)
            if int(info.get("maxInputChannels") or 0) > 0:
                return index
    except Exception:  # noqa: BLE001
        pass
    return None


def _device_attr(pyaudio_instance, index, key, default=None):
    try:
        return pyaudio_instance.get_device_info_by_index(index).get(key, default)
    except Exception:  # noqa: BLE001
        return default


def _sample_format(pyaudio_instance):
    """取 16bit 整型的 format 常量。

    **`paInt16` 是 pyaudio 的模块级常量，不在 `PyAudio` 实例上。**
    2026-09-30 真机上把形参当成模块、属性却从实例上取，
    于是每个采样率都报 `'PyAudio' object has no attribute 'paInt16'` ——
    六个全一样，又一次把真正的失败原因盖掉了。
    （所以本文件里凡是接 `PyAudio()` 实例的形参一律叫 `pyaudio_instance`，
    不再用会误导人以为可以塞模块的名字。）

    先看实例（测试替身会带上），再退回真正的模块。
    """
    value = getattr(pyaudio_instance, "paInt16", None)
    if value is not None:
        return value
    import pyaudio
    return pyaudio.paInt16


def open_input_stream(pyaudio_instance, frames_per_buffer=CHUNK, target_rate=FRAMERATE):
    """打开麦克风并返回 `MicStream`，优先按 target_rate，设备不支持时自动降级。

    `pyaudio_instance` 必须是 `pyaudio.PyAudio()` 的**实例**（不是模块）。
    调用方在 `rate != target_rate` 时用 `resample_pcm16()` 把每块转回目标采样率。

    打不开时抛 RuntimeError，并把**每个采样率的失败原因**一起带上，
    同时给出可执行的排查命令 —— 否则用户只看到
    `OSError: [Errno -9997] Invalid sample rate`，只能猜。
    """
    index = _input_device_index(pyaudio_instance)
    if index is None:
        raise RuntimeError(
            "找不到任何录音设备（树莓派 5 本身没有模拟输入，必须外接麦克风）。\n"
            "  1. USB 麦克风直接插 USB 口，然后重插一次让它重新枚举\n"
            "  2. 查看系统识别到哪些设备：arecord -l\n"
            "  3. 详细诊断：bash scripts/pi_audio_setup.sh"
        )

    name = _device_attr(pyaudio_instance, index, "name", "") or "未知"
    default_rate = int(_device_attr(pyaudio_instance, index, "defaultSampleRate", 0) or 0)

    # 目标采样率优先；其后是设备自报的默认采样率，再是常见采样率。
    rates = [target_rate]
    for rate in (default_rate,) + FALLBACK_RATES:
        if rate and rate not in rates:
            rates.append(rate)

    sample_format = _sample_format(pyaudio_instance)
    errors = []
    for rate in rates:
        frames = max(1, int(round(frames_per_buffer * rate / float(target_rate))))
        try:
            with no_alsa_error():
                stream = pyaudio_instance.open(
                    format=sample_format,
                    channels=CHANNELS,
                    rate=rate,
                    input=True,
                    input_device_index=index,
                    frames_per_buffer=frames,
                )
        except Exception as exc:  # noqa: BLE001
            errors.append("%6dHz → %s" % (rate, exc))
            continue
        if rate != target_rate:
            print("[audio] 麦克风「%s」不支持 %dHz，改用 %dHz + 软件重采样"
                  % (name, target_rate, rate))
        return MicStream(stream, rate, frames)

    # 全部失败：「设备被别的进程占用」和「采样率不支持」处理方式完全不同，
    # 所以先看一眼是不是 busy，别让两种原因共用一个含糊的提示。
    joined = "\n  ".join(errors)
    busy_hint = ""
    if "busy" in joined.lower():
        busy_hint = ("  设备报告忙碌：可能被别的程序占用（上一次 make run 没退干净？）\n"
                     "  查占用：sudo fuser -v /dev/snd/*  ，或重启后再试\n")

    raise RuntimeError(
        "麦克风「%s」(索引 %d) 无法以任何常见采样率打开：\n  %s\n%s"
        "  1. 看设备支持哪些采样率：bash scripts/pi_audio_setup.sh\n"
        "  2. 让系统层面自动转换到 16kHz：bash scripts/pi_audio_setup.sh --fix\n"
        "  3. 若插了多个麦克风，用 %s=<索引> 指定"
        % (name, index, joined, busy_hint, MIC_DEVICE_ENV)
    )


def resample_pcm16(frames, src_rate, dst_rate):
    """16bit PCM 字节流重采样（线性插值）。

    * `src_rate == dst_rate` 时**逐字节原样返回**（不做多余计算，也不改动数据）；
    * 用于把麦克风的 44.1k/48k 转成模型要的 16k，够用且只需 numpy。

    **已知取舍**：降采样时没有做抗混叠低通，所以 8kHz 以上的成分会折叠回带内。
    对语音通常无所谓 —— 语音能量集中在 300~3400Hz，房间噪声在 8kHz 以上也很弱；
    而且真要严格处理得用 150+ 抽头的 FIR，在 4GB 的 Pi 上为这点收益不值得。
    哪天真需要更高保真：`scripts/pi_audio_setup.sh --fix` 建的 `pcm.mic16k` 是
    ALSA 的 `plug`，它自带带滤波的重采样，改用那个设备即可。
    """
    if src_rate == dst_rate or not frames:
        return frames

    import numpy as np  # 延迟导入：只有真的需要重采样时才用得到

    samples = np.frombuffer(frames, dtype=np.int16)
    if samples.size < 2:
        return b""
    count = int(round(samples.size * dst_rate / float(src_rate)))
    if count <= 0:
        return b""

    # 每个输出点落在输入时间轴上的位置，取相邻两点做线性插值
    positions = np.arange(count, dtype=np.float64) * (float(src_rate) / dst_rate)
    left = np.floor(positions).astype(np.int64)
    right = np.minimum(left + 1, samples.size - 1)
    frac = positions - left
    values = (samples[left].astype(np.float64) * (1.0 - frac)
              + samples[right].astype(np.float64) * frac)
    return np.clip(np.round(values), -32768, 32767).astype(np.int16).tobytes()


# --------------------------------------------------------------------------
# 播放
# --------------------------------------------------------------------------
def resolve_audio(audio):
    """把资源名或路径解析成可用的绝对路径，找不到返回 None。"""
    if not audio:
        return None
    if os.path.isabs(audio):
        return audio if os.path.exists(audio) else None
    if os.path.exists(audio):
        return os.path.abspath(audio)
    return find_audio(audio)


def play_audio(audio, volume=100, background=False):
    """播放音频，audio 可以是 resources/ 下的文件名，也可以是完整路径。

    background=True 时把播放器丢到后台，函数立即返回 —— 用于「配乐要和下位机
    动作同时开始」的场合（例如舞蹈动作 act1~act5）。此时返回 True 只代表
    **已启动**，不代表已经播完。
    """
    target = resolve_audio(audio)
    if target is None:
        print("[audio] 找不到音频文件: %s" % audio)
        return False

    # 后台播放：命令末尾加 &，由 shell 立刻返回
    tail = " &" if background else ""
    if shutil.which("mplayer"):
        command = 'mplayer -volume %d "%s" > /dev/null 2>&1%s' % (volume, target, tail)
    elif shutil.which("ffplay"):
        command = 'ffplay -nodisp -autoexit "%s" > /dev/null 2>&1%s' % (target, tail)
    else:
        print("[audio] 未找到 mplayer/ffplay，跳过播放: %s" % target)
        return False
    return os.system(command) == 0


# --------------------------------------------------------------------------
# 录音
# --------------------------------------------------------------------------
def play_listening_cue(phase, sound="ding.wav"):
    """同步播放一次开麦提示；随后留出尾音消散时间。"""
    from playback_metrics import duration

    started = time.monotonic()
    if not play_audio(sound, background=False):
        raise RuntimeError('收音提示音播放失败：%s' % sound)
    total = duration(resolve_audio(sound))
    total_text = '未知' if total is None else '%.2f 秒' % total
    event('提示音', '%s | 总时长 %s | 实际耗时 %.2f 秒' %
          (phase, total_text, time.monotonic() - started))
    if phase == '开始收音':
        time.sleep(0.12)


def save_wave_file(filename, frames):
    """把录音数据块写成 WAV 文件（表头固定为 FRAMERATE，即 16kHz）。"""
    directory = os.path.dirname(os.path.abspath(filename))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with wave.open(filename, "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(SAMPWIDTH)
        handle.setframerate(FRAMERATE)
        handle.writeframes(b"".join(frames))


def record_wav(filename, seconds, cue=True, cue_start="ding.wav"):
    """录音 seconds 秒并写成 WAV，返回文件路径。

    cue=True 时仅在开麦前播放一次 ding，录音结束不再提示。

    设备只支持 44.1k/48k 时先按设备采样率录，再重采样到 16kHz 后才写文件 ——
    **WAV 表头永远是 16kHz**，所以识别后端（sherpa_speech.read_wav_float32
    会严格校验采样率）不需要知道底下是什么设备。
    """
    import pyaudio  # 延迟导入：只有真正录音时才需要

    save_directory = os.path.dirname(os.path.abspath(filename))
    os.makedirs(save_directory, exist_ok=True)
    if cue:
        play_listening_cue('开始收音', cue_start)

    with no_alsa_error():
        audio = pyaudio.PyAudio()
    mic = None
    frames = []
    try:
        mic = open_input_stream(audio, CHUNK)
        total_chunks = max(1, int(round(seconds * mic.rate / float(mic.frames_per_buffer))))
        print("开始录音（约 %.1f 秒）" % (total_chunks * mic.frames_per_buffer / float(mic.rate)))
        for _ in range(total_chunks):
            frames.append(mic.stream.read(mic.frames_per_buffer))
            print(".", end="", flush=True)
    finally:
        if mic is not None:
            try:
                mic.stream.stop_stream()
                mic.stream.close()
            except Exception:  # noqa: BLE001
                pass
        audio.terminate()
    print("\n录音结束")

    # 采样率一致时 resample_pcm16 原样返回，等于什么都没做
    save_wave_file(filename, [resample_pcm16(b"".join(frames), mic.rate, FRAMERATE)])
    return filename
