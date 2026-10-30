# Silero 人声检测

用于区分人声和非人声噪声，不用于识别人是谁。

- 来源：[sherpa-onnx 官方模型说明](https://k2-fsa.github.io/sherpa/onnx/vad/silero-vad.html)
- 下载：https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
- 本次文件大小：643854 字节
- SHA256：`9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6`
- 检查：从 pi 目录运行 `.venv/bin/python scripts/smoke_listening.py`

标准 `scripts/prepare_sherpa_models.py` 会准备此模型，并验证上述哈希。
