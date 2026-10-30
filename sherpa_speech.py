"""sherpa-onnx：蜂后唤醒词检测与离线 SenseVoice 台词识别。

模型：models/kws、models/sensevoice；可用 SHERPA_KWS_DIR / SHERPA_ASR_DIR 覆盖。
准备：python scripts/prepare_sherpa_models.py。依赖在实际识别时加载。
"""
import os
import re
import wave

from paths import project_path

SAMPLE_RATE = 16000

# SenseVoice 输出里可能夹带的特殊标签，打印前清掉
_TAGS = re.compile(r"<\|[^|]*\|>")

KWS_DIR_ENV = "SHERPA_KWS_DIR"
ASR_DIR_ENV = "SHERPA_ASR_DIR"
KEYWORDS_ENV = "KWS_KEYWORDS"
KWS_THRESHOLD_ENV = "KWS_THRESHOLD"
KWS_SCORE_ENV = "KWS_SCORE"
ASR_LANG_ENV = "SHERPA_ASR_LANGUAGE"
THREADS_ENV = "SHERPA_THREADS"

DEFAULT_KWS_DIR = "models/kws"
DEFAULT_ASR_DIR = "models/sensevoice"

# 各模型按优先级挑选（优先 int8，其次 fp32；优先固定 epoch）
_ENCODER_PREFS = (
    "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "encoder-epoch-12-avg-2-chunk-16-left-64.onnx",
    "encoder*chunk-16-left-64.int8.onnx",
    "encoder*.int8.onnx",
    "encoder*.onnx",
)
_DECODER_PREFS = (
    "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "decoder-epoch-12-avg-2-chunk-16-left-64.onnx",
    "decoder*chunk-16-left-64.int8.onnx",
    "decoder*.int8.onnx",
    "decoder*.onnx",
)
_JOINER_PREFS = (
    "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "joiner-epoch-12-avg-2-chunk-16-left-64.onnx",
    "joiner*chunk-16-left-64.int8.onnx",
    "joiner*.int8.onnx",
    "joiner*.onnx",
)
_ASR_MODEL_PREFS = ("model.int8.onnx", "model.onnx")


def _dir(env_name, default):
    return project_path(os.getenv(env_name, default))


def kws_dir():
    return _dir(KWS_DIR_ENV, DEFAULT_KWS_DIR)


def asr_dir():
    return _dir(ASR_DIR_ENV, DEFAULT_ASR_DIR)


def keywords_file():
    return os.getenv(KEYWORDS_ENV) or os.path.join(kws_dir(), "keywords.txt")


def _pick(directory, patterns):
    """在目录里按优先级找第一个存在的文件，找不到返回 None。"""
    if not os.path.isdir(directory):
        return None
    import glob

    for pat in patterns:
        hits = sorted(glob.glob(os.path.join(directory, pat)))
        if hits:
            return hits[0]
    return None


def _sherpa():
    """惰性导入 sherpa_onnx；没装返回 None。"""
    try:
        import sherpa_onnx  # noqa

        return sherpa_onnx
    except Exception:  # noqa: BLE001
        return None


def kws_model_files():
    """返回 (encoder, decoder, joiner, tokens) 路径，缺任意一个返回 None。"""
    directory = kws_dir()
    files = (
        _pick(directory, _ENCODER_PREFS),
        _pick(directory, _DECODER_PREFS),
        _pick(directory, _JOINER_PREFS),
    )
    tokens = os.path.join(directory, "tokens.txt")
    if any(f is None for f in files) or not os.path.exists(tokens):
        return None
    return files + (tokens,)


def asr_model_files():
    directory = asr_dir()
    model = _pick(directory, _ASR_MODEL_PREFS)
    tokens = os.path.join(directory, "tokens.txt")
    if model is None or not os.path.exists(tokens):
        return None
    return model, tokens


def kws_ready():
    """唤醒后端是否可用：装了 sherpa + 有模型 + 有 keywords.txt。"""
    return (_sherpa() is not None
            and kws_model_files() is not None
            and os.path.exists(keywords_file()))


def kws_readiness():
    """KWS 是否就绪；未就绪时给出**具体原因**，供脚本给出可操作的提示。

    返回 (ok, detail)。与 `kws_ready()` 判定一致，只是把「为什么不行」说清楚 ——
    否则用户只会看到「后端不可用」，不知道该装 sherpa 还是该准备模型。
    """
    if _sherpa() is None:
        return False, "sherpa-onnx 未安装（pip install sherpa-onnx）"
    if kws_model_files() is None:
        return False, "KWS 模型文件不全（期望目录 %s，需含 encoder/decoder/joiner 与 tokens.txt）" % kws_dir()
    if not os.path.exists(keywords_file()):
        return False, ("缺唤醒词文件 %s —— 改 models/kws/keywords_raw.txt 后跑"
                       " python3 scripts/make_keywords.py" % keywords_file())
    return True, "KWS 就绪（唤醒词文件：%s）" % keywords_file()


def asr_ready():
    """识别后端是否可用：装了 sherpa + 有 SenseVoice 模型。"""
    return _sherpa() is not None and asr_model_files() is not None


# --------------------------------------------------------------------------
# 读取 WAV -> float32 单声道（sherpa 的输入格式）
# --------------------------------------------------------------------------
def read_wav_float32(path, target_sr=SAMPLE_RATE):
    import numpy as np

    with wave.open(path, "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if channels != 1 or width != 2:
        raise ValueError("只支持单声道 16bit PCM WAV：%s" % path)
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if rate != target_sr:
        raise ValueError("采样率需为 %d，实际 %d：%s" % (target_sr, rate, path))
    return samples


# --------------------------------------------------------------------------
# 唤醒词检测（KWS）
# --------------------------------------------------------------------------
class KwsDetector:
    """流式唤醒词检测器。每来一块 16k float32 音频调一次 detect()。"""

    def __init__(self, model_dir=None, keywords=None, num_threads=None,
                 score=None, threshold=None, sample_rate=SAMPLE_RATE):
        sherpa_onnx = _sherpa()
        if sherpa_onnx is None:
            raise RuntimeError("未安装 sherpa-onnx，无法使用 KWS 唤醒")

        files = kws_model_files()
        if files is None:
            raise RuntimeError("KWS 模型不完整，请先运行 scripts/prepare_sherpa_models.py")
        encoder, decoder, joiner, tokens = files

        keywords = keywords or keywords_file()
        if not os.path.exists(keywords):
            raise RuntimeError("找不到唤醒词文件：%s" % keywords)

        num_threads = num_threads or int(os.getenv(THREADS_ENV, "1"))
        score = float(os.getenv(KWS_SCORE_ENV, "2.0")) if score is None else score
        threshold = float(os.getenv(KWS_THRESHOLD_ENV, "0.25")) if threshold is None else threshold

        self.sample_rate = sample_rate
        self.spotter = sherpa_onnx.KeywordSpotter(
            tokens=tokens,
            encoder=encoder,
            decoder=decoder,
            joiner=joiner,
            keywords_file=keywords,
            num_threads=num_threads,
            sample_rate=sample_rate,
            keywords_score=score,
            keywords_threshold=threshold,
            provider="cpu",
        )
        self.stream = self.spotter.create_stream()

    def reset(self):
        """复位解码状态（命中后必须调用，否则历史会影响下一句）。"""
        self.stream = self.spotter.create_stream()

    def detect(self, samples):
        import numpy as np

        self.stream.accept_waveform(self.sample_rate, np.asarray(samples, dtype=np.float32))
        while self.spotter.is_ready(self.stream):
            self.spotter.decode_stream(self.stream)
        result = self.spotter.get_result(self.stream)
        keyword = result if isinstance(result, str) else getattr(result, "keyword", "")
        if keyword:
            self.reset()
        return keyword


# --------------------------------------------------------------------------
# 语音识别（SenseVoice）
# --------------------------------------------------------------------------
class AsrRecognizer:
    """整段音频 -> 文字（唤醒后录一句话再整体识别）。"""

    def __init__(self, model_dir=None, num_threads=None, language=None,
                 use_itn=True, sample_rate=SAMPLE_RATE):
        sherpa_onnx = _sherpa()
        if sherpa_onnx is None:
            raise RuntimeError("未安装 sherpa-onnx，无法使用 SenseVoice 识别")

        files = asr_model_files()
        if files is None:
            raise RuntimeError("SenseVoice 模型不完整，请先运行 scripts/prepare_sherpa_models.py")
        model, tokens = files

        num_threads = num_threads or int(os.getenv(THREADS_ENV, "2"))
        language = language or os.getenv(ASR_LANG_ENV, "zh")
        self.sample_rate = sample_rate
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model,
            tokens=tokens,
            num_threads=num_threads,
            sample_rate=sample_rate,
            language=language,
            use_itn=use_itn,
            provider="cpu",
        )

    def transcribe(self, samples):
        import numpy as np

        stream = self.recognizer.create_stream()
        stream.accept_waveform(self.sample_rate, np.asarray(samples, dtype=np.float32))
        self.recognizer.decode_stream(stream)
        return _clean_tags(stream.result.text)


def _clean_tags(text):
    """去掉 SenseVoice 输出里夹带的 <|...|> 标签。"""
    return _TAGS.sub("", text or "").strip()


# --------------------------------------------------------------------------
# 惰性单例
# --------------------------------------------------------------------------
_kws = None
_asr = None


def get_kws():
    global _kws
    if _kws is None:
        _kws = KwsDetector()
    return _kws


def get_asr():
    global _asr
    if _asr is None:
        _asr = AsrRecognizer()
    return _asr


def transcribe_wav(path):
    """便捷函数：WAV 文件 -> 文本。"""
    return get_asr().transcribe(read_wav_float32(path))
