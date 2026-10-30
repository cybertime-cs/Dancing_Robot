# Listening Cues Implementation Plan

**Goal:** 为唤醒和每次台词收音增加前后短嗡提示音，仅保存本地修改。

**Architecture:** `audio.py` 提供同步提示音播放函数。三个录音入口在打开麦克风前、正常释放设备后调用；连续台词识别由 `speech_recog.py` 在关麦后并行执行结束提示和语音转文字。

**Tech Stack:** Python 标准库、既有 mplayer/ffplay 播放器、unittest 和替代硬件。

## 1. 先验证设备生命周期

- [x] 新增 `FENGHOU/tests/test_listening_cues.py`，实际运行 `wait_for_wake()`、`record_utterance()` 和 `record_wav()`。
- [x] 对正常路径断言顺序：`开始提示 < open < close < terminate < 结束提示`。
- [x] 对异常和 Ctrl+C 断言清理设备且无结束提示，对未匹配后的下一句断言再次产生一对提示。
- [x] 运行 `.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -p test_listening_cues.py -v`，确认因缺少提示而失败。

## 2. 最小实现

- [x] 在 `audio.py` 实现 `play_listening_cue(phase, sound='listen_buzz.wav')`：同步播放、失败报错、记录时长；开始提示播放后等待 0.12 秒。
- [x] 唤醒循环改为命中后退出循环，先走清理逻辑，再播放结束提示并返回唤醒词。
- [x] 连续台词在 VAD 初始化后、开麦前提示；正常关闭并保存录音后由识别入口并行播放结束提示和执行推理。
- [x] 定长录音默认提示文件改为 `listen_buzz.wav`，沿用禁用和自定义参数。
- [x] 将 CC0 熊蜂振翅录音剪辑成 16 kHz 单声道 PCM16、约 0.6 秒的提示音，叠加轻微科幻共振并淡入淡出；保持 `audio_durations.json` 与实际文件一致，记录素材来源。
- [x] 既有纯软件录音测试替代提示音播放，避免外设依赖。

## 3. 验证与交付

- [x] 新增用例及完整 `scripts/selftest.py` 通过。
- [x] `main.py --check`、`main.py --dry-run --demo` 通过，且纯模拟不调用提示音播放。
- [x] WAV 时长、文件大小和时长索引一致。
- [x] 更新 README、使用指南和 CHANGELOG，说明前后提示的含义及本地尚未部署状态。
- [x] 仅提交本次明确列出的文件，不包含用户另行新增的舞蹈背景资料。
