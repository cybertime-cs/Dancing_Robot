"""一次唤醒监听：命中后关闭麦克风，将控制权交还剧本。"""
from audio import no_alsa_error, open_input_stream, resample_pcm16, play_listening_cue
from runtime_log import event

CHUNK = 1600


def wait_for_wake():
    """等待配置的唤醒词；失败抛异常，Ctrl+C 释放设备。"""
    import numpy as np
    import pyaudio
    from sherpa_speech import KwsDetector, SAMPLE_RATE

    detector = KwsDetector()
    play_listening_cue('开始收音')
    audio = None
    mic = None
    try:
        with no_alsa_error():
            audio = pyaudio.PyAudio()
        mic = open_input_stream(audio, CHUNK, target_rate=SAMPLE_RATE)
        event('唤醒', '等待“蜂后”')
        while True:
            data = mic.stream.read(mic.frames_per_buffer, exception_on_overflow=False)
            data = resample_pcm16(data, mic.rate, SAMPLE_RATE)
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            keyword = detector.detect(samples)
            if keyword:
                event('唤醒', '已命中：%s' % keyword)
                break
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
    return keyword
