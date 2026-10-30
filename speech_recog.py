"""录音并通过 sherpa-onnx SenseVoice 返回台词文本。"""
import os
import time
from functools import lru_cache
from runtime_log import event
from audio import record_wav
from paths import ensure_temp_record_dir

RECORD_SECONDS = 3.75


def resolve_asr_backend():
    return 'sherpa'


def backend_summary():
    from sherpa_speech import asr_dir
    return 'sherpa-onnx SenseVoice（%s）' % asr_dir()


def _sherpa_transcribe(wav_path):
    from sherpa_speech import transcribe_wav
    return transcribe_wav(wav_path)


@lru_cache(maxsize=1)
def prepare_listening():
    """在开麦之前完成模型加载和首次推理，后续台词复用已就绪的识别器。"""
    import numpy as np
    from sherpa_speech import get_asr, SAMPLE_RATE

    started = time.monotonic()
    event('语音准备', '正在加载并预热识别模型；就绪后开始监听')
    get_asr().transcribe(np.zeros(SAMPLE_RATE // 2, dtype=np.float32))
    event('语音准备', '识别模型已就绪 | 准备耗时 %.2f 秒' % (time.monotonic() - started))


def speech_recog(seconds=None, cue=True):
    prepare_listening()
    wav_path = os.path.join(ensure_temp_record_dir(), 'temp.wav')
    record_wav(wav_path, RECORD_SECONDS if seconds is None else seconds, cue=cue)
    return _sherpa_transcribe(wav_path).replace(' ', '')


def listen_for_line(settings=None, *, cue=True):
    """等待一句话并关麦识别；同轮重试通过 cue=False 保持安静。"""
    from utterance import record_utterance
    prepare_listening()
    wav_path = os.path.join(ensure_temp_record_dir(), 'utterance.wav')
    record_utterance(wav_path, settings, cue=cue)
    started = time.monotonic()
    text = _sherpa_transcribe(wav_path).replace(' ', '')
    event('识别', '转文字 %.2f 秒 | %s' %
          (time.monotonic() - started, text or '空白'))
    return text


if __name__ == '__main__':
    try:
        while True:
            print(speech_recog())
    except KeyboardInterrupt:
        pass
