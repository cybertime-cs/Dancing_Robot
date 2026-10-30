"""连续等待说话，以短时能量和句尾静音分句；不依赖额外模型。"""
from collections import deque
import math
from pathlib import Path
from runtime_log import event

DEFAULT_LISTENING = {
    'backend': 'energy',
    'vad_threshold': 0.65,
    'energy_threshold': 350,
    'min_speech_seconds': 0.20,
    'silence_seconds': 0.90,
    'pre_roll_seconds': 0.30,
    'max_utterance_seconds': 25,
}
FRAME_SECONDS = 0.02


def listening_settings(settings=None):
    values = dict(DEFAULT_LISTENING)
    values.update(settings or {})
    if set(values) != set(DEFAULT_LISTENING):
        raise ValueError('未知监听配置项')
    for key, value in values.items():
        if key == 'backend':
            if value not in ('energy', 'silero'):
                raise ValueError('未知人声检测后端')
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('监听配置必须是有限正数：%s' % key)
    if not 1 <= values['energy_threshold'] <= 32768:
        raise ValueError('energy_threshold 必须在 1~32768 之间')
    if not 0 < values['vad_threshold'] < 1:
        raise ValueError('vad_threshold 必须在 0~1 之间')
    if not (FRAME_SECONDS <= values['min_speech_seconds'] < values['max_utterance_seconds'] <= 120):
        raise ValueError('说话时间范围无效')
    if not FRAME_SECONDS <= values['silence_seconds'] <= 5 or not FRAME_SECONDS <= values['pre_roll_seconds'] <= 2:
        raise ValueError('句尾静音或前置缓存时间无效')
    return values


class UtteranceSegmenter:
    """输入固定 20ms 单声道 PCM16；只在完整句尾返回音频。

    长时间静音仅占用前置缓存；超过最长句长则整句丢弃，避免截断台词误触发。
    """
    def __init__(self, settings=None, frame_seconds=FRAME_SECONDS):
        self.settings = listening_settings(settings)
        self.frame_seconds = frame_seconds
        self.frame_samples = round(16000 * frame_seconds)
        self.pre = deque(maxlen=math.ceil(self.settings['pre_roll_seconds'] / self.frame_seconds))
        self.frames = []
        self.voiced = 0
        self.quiet = 0
        self.discarding = False
        self.dropped = 0

    def reset(self):
        self.pre.clear()
        self.frames.clear()
        self.voiced = self.quiet = 0
        self.discarding = False

    def feed(self, pcm, speech=None):
        import numpy as np
        samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32)
        if len(samples) != self.frame_samples:
            raise ValueError('分句输入帧长度不符')
        if speech is None:
            speech = float(np.sqrt(np.mean(samples * samples))) >= self.settings['energy_threshold']
        self.quiet = 0 if speech else self.quiet + 1
        end = self.quiet >= math.ceil(self.settings['silence_seconds'] / self.frame_seconds)
        if self.discarding:
            if end:
                self.reset()
            return None
        if not self.frames:
            if not speech:
                self.pre.append(pcm)
                return None
            self.frames = list(self.pre)
            self.pre.clear()
            self.quiet = 0
        self.frames.append(pcm)
        if speech:
            self.voiced += 1
        if end:
            result = (b''.join(self.frames) if self.voiced >= math.ceil(self.settings['min_speech_seconds'] / self.frame_seconds)
                      else None)
            self.reset()
            return result
        if len(self.frames) * self.frame_seconds >= self.settings['max_utterance_seconds']:
            self.frames.clear()
            self.pre.clear()
            self.discarding = True
            self.dropped += 1
        return None


class SileroSegmenter(UtteranceSegmenter):
    """用神经网络检测人声，沿用有界缓存和超长整句拒绝机制。"""
    def __init__(self, settings=None):
        import sherpa_onnx
        super().__init__(settings, frame_seconds=512/16000)
        path = Path(__file__).resolve().parent / 'models/vad/silero_vad.onnx'
        if not path.is_file():
            raise RuntimeError('缺少人声检测模型：%s' % path)
        config = sherpa_onnx.VadModelConfig()
        config.sample_rate = 16000
        config.num_threads = 1
        config.silero_vad.model = str(path)
        config.silero_vad.threshold = self.settings['vad_threshold']
        config.silero_vad.min_silence_duration = self.frame_seconds
        config.silero_vad.min_speech_duration = self.frame_seconds
        config.silero_vad.max_speech_duration = 120
        self.model = sherpa_onnx.VadModel.create(config)

    def reset(self):
        super().reset()
        self.model.reset()

    def feed(self, pcm):
        import numpy as np
        samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
        return super().feed(pcm, speech=self.model.is_speech(samples))


def record_utterance(filename, settings=None, *, cue=True):
    """等待一句并关麦；新一轮开麦可提示，重试不再鸣响。"""
    import pyaudio
    from audio import no_alsa_error, open_input_stream, resample_pcm16, save_wave_file, play_listening_cue

    settings = listening_settings(settings)
    segmenter = SileroSegmenter(settings) if settings['backend'] == 'silero' else UtteranceSegmenter(settings)
    frame_bytes = segmenter.frame_samples * 2
    audio = None
    mic = None
    pending = b''
    result = None
    if cue:
        play_listening_cue('开始收音')
    try:
        with no_alsa_error():
            audio = pyaudio.PyAudio()
        mic = open_input_stream(audio, segmenter.frame_samples, target_rate=16000)
        event('监听', '等待一句台词 | %s | 句尾停顿 %.2f 秒' % (settings['backend'], settings['silence_seconds']))
        while result is None:
            data = mic.stream.read(mic.frames_per_buffer, exception_on_overflow=False)
            if not data:
                raise RuntimeError('麦克风未返回音频')
            pending += resample_pcm16(data, mic.rate, 16000)
            while len(pending) >= frame_bytes and result is None:
                result = segmenter.feed(pending[:frame_bytes])
                pending = pending[frame_bytes:]
            if segmenter.dropped:
                event('忽略', '连续声音超过 %.0f 秒，整段丢弃；等待安静后继续' % settings['max_utterance_seconds'])
                segmenter.dropped = 0
    finally:
        try:
            if mic is not None:
                try:
                    mic.stream.stop_stream()
                finally:
                    mic.stream.close()
        finally:
            if audio is not None:
                audio.terminate()
    save_wave_file(filename, [result])
    quiet_seconds = math.ceil(settings['silence_seconds'] / segmenter.frame_seconds) * segmenter.frame_seconds
    event('收音', '结束 | 录音片段 %.2f 秒 | 判定句尾静音 %.2f 秒' %
          (len(result) / 32000, quiet_seconds))
    return filename
