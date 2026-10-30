# 蜂后唤醒模型

`keywords_raw.txt` 是唤醒词来源，`keywords.txt` 是运行时词表。
修改后从 pi 目录运行 `python scripts/make_keywords.py`。
保留 encoder、decoder、joiner 三个 ONNX 文件以及 tokens.txt；模型准备由 `scripts/prepare_sherpa_models.py` 完成。
部署与使用统一见 `../../README.md`。
