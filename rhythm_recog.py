# TODO 韵律识别
import wave
from numpy.linalg import norm
from numpy import array
import librosa
import pyaudio
from dtw import dtw
import numpy as np
import os


framerate = 16000
NUM_SAMPLES = 2000
channels = 1
sampwidth = 2
TIME = 10


def save_wave_file(filename, data):
    wf = wave.open(filename, "wb")
    wf.setnchannels(channels)
    wf.setsampwidth(sampwidth)
    wf.setframerate(framerate)
    wf.writeframes(b"".join(data))
    wf.close()


def record_music(f, time=5):
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=framerate,
        input=True,
        frames_per_buffer=NUM_SAMPLES,
    )
    my_buf = []
    count = 0
    print("开始录音")
    print("录音中({}s)".format(str(time)))
    while count < TIME * time:
        string_audio_data = stream.read(NUM_SAMPLES)
        my_buf.append(string_audio_data)
        count += 1
        print(".", end="", flush=True)
    print("录音结束")
    save_wave_file(f, my_buf)
    stream.close()

def play_audio(audio_file):
    os.system('mplayer %s' % audio_file)


def rhythm_recog():
    record_music('./temp_record/song_temp.MP3', time=13)
    play_audio('resources/finish.MP3')
    all_data = np.load('beatDatabase.npy', allow_pickle=True)
    beat_database = all_data.item()

    testAudio = "./temp_record/song_temp.MP3"
    y, sr = librosa.load(testAudio)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_frames = librosa.feature.delta(beat_frames)

    x = array(beat_frames).reshape(-1, 1)

    compare_result = {}

    for songID in beat_database.keys():
        y = beat_database[songID]
        y = array(y).reshape(-1, 1)
        dist, cost, acc, path = dtw(x, y, dist=lambda x, y: norm(x - y, ord=1))
        print('Minimum distance found for ' + ": ", dist)
        compare_result[songID] = dist

    matched_song = min(compare_result, key=compare_result.get)

    print("识别结果为" + matched_song)
    return matched_song, compare_result
   


if __name__ == '__main__':
    # 测试代码
    print(rhythm_recog())
