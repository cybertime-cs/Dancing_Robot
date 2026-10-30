"""无硬件模型验证：静音 KWS 解码、用项目配音验证 SenseVoice。不发声、不发串口。"""
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import numpy as np
    from sherpa_speech import KwsDetector, transcribe_wav
    from paths import find_audio
    started = time.monotonic()
    detector = KwsDetector()
    for _ in range(20):
        if detector.detect(np.zeros(1600, dtype=np.float32)):
            raise RuntimeError('静音不应触发唤醒')
    print('KWS 模型加载与静音解码通过（不代表真人唤醒测试通过）', flush=True)
    del detector
    with tempfile.TemporaryDirectory() as directory:
        wav = str(Path(directory) / 'voice.wav')
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', find_audio('1-1'),
                        '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', wav], check=True)
        text = transcribe_wav(wav)
        if not text.strip():
            raise RuntimeError('配音识别结果为空')
        print('SenseVoice 实际识别结果：%s' % text, flush=True)
    print('模型验证完成，耗时 %.1f 秒；未访问麦克风、喇叭或串口。' % (time.monotonic() - started))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
