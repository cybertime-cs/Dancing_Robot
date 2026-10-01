import wave
import pyaudio
import os
import struct

def play_wav_with_volume(filename="1.wav", volume_gain=2.0):
    """
    播放WAV文件并支持音量增益
    :param filename: 文件名
    :param volume_gain: 音量增益倍数，1.0为原音量，2.0为两倍音量，最大建议不超过3.0避免爆音
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, filename)

    if not os.path.exists(file_path):
        print(f"错误：找不到文件 {file_path}")
        return

    try:
        wf = wave.open(file_path, 'rb')
        p = pyaudio.PyAudio()

        # 从WAV文件头获取参数
        sample_width = wf.getsampwidth()  # 采样位深（字节数）
        channels = wf.getnchannels()      # 声道数
        rate = wf.getframerate()          # 采样率

        # 打开输出流
        stream = p.open(
            format=p.get_format_from_width(sample_width),
            channels=channels,
            rate=rate,
            output=True
        )

        # 分块读取并处理音量
        chunk_size = 1024
        while True:
            data = wf.readframes(chunk_size)
            if not data:
                break

            # 将字节数据转换为数值列表进行增益处理
            if sample_width == 2:  # 16位PCM
                fmt = f"<{len(data)//2}h"  # 小端序，有符号短整型
                samples = list(struct.unpack(fmt, data))
                # 应用增益并限制在16位范围内 [-32768, 32767]
                amplified = [max(-32768, min(32767, int(s * volume_gain))) for s in samples]
                # 转回字节数据
                data = struct.pack(fmt, *amplified)
            elif sample_width == 1:  # 8位PCM（无符号）
                fmt = f"<{len(data)}B"
                samples = list(struct.unpack(fmt, data))
                amplified = [max(0, min(255, int(s * volume_gain))) for s in samples]
                data = struct.pack(fmt, *amplified)

            stream.write(data)

        stream.stop_stream()
        stream.close()
        wf.close()
        p.terminate()

    except Exception as e:
        print(f"播放失败：{e}")

# 调用示例：播放1.wav，音量放大2倍
play_wav_with_volume("1.wav", volume_gain=3.0)