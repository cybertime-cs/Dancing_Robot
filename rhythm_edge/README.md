# 树莓派离线韵律识别验证

本目录是独立方案，不调用或修改原有的 `rhythm_recog.py`、`rhythm_train.py` 和 `beatDatabase.npy`。代码只依赖 Python 标准库与 NumPy；识别阶段不需要网络、Librosa 或 DTW。

## 方法

1. 扫描训练目录的 WAV 文件，只接收时长约 15 秒（14.9 至 17.0 秒）的源文件，并统一取前 15 秒。文件名直接成为类别名，没有写死任何歌曲名称。超长文件会跳过并在建库结果中列出。
2. 将音频转为 8 kHz 单声道，按 32 ms 步长提取四个频带的能量变化，保留鼓点及节奏强弱的时间模式。
3. 对录音中的 8 秒窗口做归一化相关匹配，在每段参考音频中寻找最合适的位置。这样允许录音从歌曲中间开始，也能减轻音量变化的影响。
4. 最高分及其与第二名的差距都达标才返回文件名，否则返回 `null`，避免任何录音都被硬分到已有类别。

特征库为压缩 `.npz`，不保存原始音频，也不使用 pickle。当前五段合格源文件生成的特征库约 25 KB。日后更换音频，只需重新建库；若新的 `choice.wav` 换成约 15 秒的文件，它也会自动加入。

## 使用

在项目根目录运行：

```bash
python3 rhythm_edge/recognizer.py build --audio-dir rhythm_train --database rhythm_edge/rhythm_database.npz --overwrite
python3 rhythm_edge/recognizer.py recognize /path/to/recording.wav --database rhythm_edge/rhythm_database.npz
python3 rhythm_edge/validate.py --audio-dir rhythm_train --database rhythm_edge/rhythm_database.npz
```

树莓派装有 ALSA `arecord` 时，也可直接录制 15 秒并识别：

```bash
python3 rhythm_edge/recognizer.py listen --database rhythm_edge/rhythm_database.npz --device default --seconds 15
```

识别结果是 JSON。`name` 为匹配的文件名；证据不足时为 `null`。`score` 是最佳归一化相关分数，`margin` 是第一名与第二名的差距。门限可通过 `--min-score` 和 `--min-margin` 调整。录音文件需为未压缩 PCM WAV，采样率至少 8 kHz。

在其他 Python 文件中调用时：

```python
from rhythm_edge.recognizer import RhythmRecognizer

recognizer = RhythmRecognizer("rhythm_edge/rhythm_database.npz")
result = recognizer.recognize_wav("/path/to/recording.wav")
matched_song = result.name  # None 表示未识别
```

## 本轮验证范围

目前 `choice.wav` 为约 106 秒，因此按通用时长规则跳过。其余五段参与建库。使用这五段音频的原始片段、音量及噪声变化片段、播放速度提高 2% 的片段进行检查，15 次均返回正确类别；把待测类别从库中移除后，5 次均返回未识别。

这些结果来自同一批源文件的变换片段，不能当作真实麦克风录音准确率。上机后应测试扬声器到麦克风的实际链路，再根据误识别和拒识情况调整统一门限。识别耗时也需要在目标树莓派上实测。
