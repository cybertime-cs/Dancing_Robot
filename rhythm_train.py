import librosa
import os
import numpy as np

audioList = os.listdir('/path/to/songs') # 音乐文件夹路径
raw_audioList = {}
beat_database = {}
for tmp in audioList:
    audioName = os.path.join(tmp)
    if audioName.endswith('.WAV') or audioName.endswith('.MP3'):
        y, sr = librosa.load(audioName)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_frames = librosa.feature.delta(beat_frames)
        beat_database[audioName] = beat_frames
np.save('beatDatabase.npy', beat_database) # 可以改变生成的路径