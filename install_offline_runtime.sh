#!/usr/bin/env bash
# 仅用于首次安装依赖和下载模型；之后 yinhe_robot.py 可离线运行。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_ARCHIVE="sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2"
MODEL_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${MODEL_ARCHIVE}"
VAD_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"

cd "$ROOT_DIR"
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt

mkdir -p models/asr
curl -fL --retry 3 -o "/tmp/${MODEL_ARCHIVE}" "$MODEL_URL"
tar -xjf "/tmp/${MODEL_ARCHIVE}" --strip-components=1 -C models/asr
rm -f "/tmp/${MODEL_ARCHIVE}"
curl -fL --retry 3 -o models/silero_vad.onnx "$VAD_URL"

echo "依赖和本地模型安装完成。请另行将机器人 SDK 的 datapackage.py 放入本目录。"
