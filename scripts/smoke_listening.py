"""无需外设验证真实 Silero 分句：静音、合成非人声及项目配音。"""
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    import numpy as np
    from utterance import SileroSegmenter
    from queen_robot.queen_script import load_script
    from paths import find_audio
    from sherpa_speech import transcribe_wav
    settings=load_script()['listening']
    def segment(samples):
        detector=SileroSegmenter(settings)
        chunks=[]
        pcm=samples.astype('<i2').tobytes()
        for start in range(0,len(pcm)-1023,1024):
            result=detector.feed(pcm[start:start+1024])
            if result is not None: chunks.append(result)
        return chunks
    if segment(np.zeros(16000*3)):
        raise RuntimeError('静音被误判为人声')
    tone=np.sin(np.arange(16000*2)*2*np.pi*1000/16000)*5000
    if segment(np.concatenate([tone,np.zeros(16000)])):
        raise RuntimeError('合成单频噪声被误判为人声')
    with tempfile.TemporaryDirectory() as directory:
        wav=Path(directory)/'input.wav'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',find_audio('1-1'),'-ar','16000','-ac','1','-c:a','pcm_s16le',str(wav)],check=True)
        with wave.open(str(wav),'rb') as handle:
            samples=np.frombuffer(handle.readframes(handle.getnframes()),dtype='<i2')
        chunks=segment(np.concatenate([np.zeros(8000),samples,np.zeros(16000*2)]))
        if not chunks: raise RuntimeError('未检出配音中的人声')
        from audio import save_wave_file
        save_wave_file(str(wav),chunks)
        text=transcribe_wav(str(wav))
        if not text: raise RuntimeError('分句后未能识别配音')
        print('Silero 通过：静音和单频噪声无片段；配音分出 %d 段，识别：%s'%(len(chunks),text))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
