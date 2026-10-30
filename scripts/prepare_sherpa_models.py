#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""准备 sherpa-onnx 模型（KWS 唤醒词 + SenseVoice 识别）。

两种来源：
    1) 从本地已有的模型目录复制（推荐，尤其是和「语音」项目共用时不重复下载）
       python scripts/prepare_sherpa_models.py --from "F:/agent ws/raspi/语音/voice_assistant/models"
    2) 联网下载（GitHub 官方 + 国内镜像按顺序重试）
       python scripts/prepare_sherpa_models.py

不带参数时会自动判断：环境变量 SHERPA_SOURCE_MODELS 或同级 voice_assistant/models
存在就复制，否则下载。

其它参数：
    --kws-only / --asr-only   只准备其中一种
    --force                   已有也重新准备
    --no-keywords             不自动生成 keywords.txt

模型体积：KWS 约 36M，SenseVoice(int8) 约 230M。
"""
from __future__ import annotations

import os
import shutil
import sys
import tarfile
import time
import urllib.request
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
VAD_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx'
VAD_SHA256 = '9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6'

GH = "https://github.com/k2-fsa/sherpa-onnx/releases/download/{tag}/{name}.tar.bz2"
PROXIES = ["https://gh-proxy.com/", "https://ghproxy.net/", ""]

SPECS = {
    "kws": {
        "tag": "kws-models",
        "name": "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01",
        "dest": MODELS_DIR / "kws",
        "ready": [
            "tokens.txt",
            "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
            "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
            "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
        ],
    },
    "asr": {
        "tag": "asr-models",
        # int8 版本 155MB；fp32 近 1GB，Pi 上没必要
        "name": "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
        "dest": MODELS_DIR / "sensevoice",
        "ready": ["model.int8.onnx", "tokens.txt"],
    },
}


def log(msg):
    print(msg, flush=True)


def _ready(cfg: dict) -> bool:
    dest = Path(cfg["dest"])
    return all((dest / n).is_file() and (dest / n).stat().st_size > 0 for n in cfg["ready"])


def _copy_from(src_root: Path, cfg: dict) -> bool:
    """从某个模型根目录复制运行必需文件。

    只复制 cfg["ready"] 里列出的模型文件 —— **不要**复制来源里的
    keywords*.txt：唤醒词是每个项目自己的配置，越权覆盖会让人莫名其妙。
    """
    src = src_root / Path(cfg["dest"]).name
    if not src.is_dir():
        return False
    dest = Path(cfg["dest"])
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in cfg["ready"]:
        s = src / name
        if s.is_file():
            shutil.copy2(s, dest / name)
            copied += 1
    log("[copy] %s <- %s（%d 个文件）" % (dest, src, copied))
    return _ready(cfg)


def _safe_extract(tf: tarfile.TarFile, dest: Path) -> None:
    """拒绝目录穿越与链接成员（允许第三方代理，故不无条件信任压缩包）。"""
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for member in tf.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest)):
            raise ValueError("压缩包包含越界路径，拒绝解压：%s" % member.name)
        if member.issym() or member.islnk() or member.isdev() or member.isfifo():
            raise ValueError("压缩包包含不安全成员，拒绝解压：%s" % member.name)
    tf.extractall(dest)


def _download(url: str, dst: Path) -> bool:
    log("  尝试：%s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length", 0))
            got = 0
            t0 = time.time()
            last = 0.0
            with open(dst, "wb") as f:
                while True:
                    chunk = r.read(512 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    pct = got * 100 / total if total else 0
                    if pct - last >= 10 or got == total:
                        speed = got / max(time.time() - t0, 0.001) / 1024
                        log("  %5.1f%%  %.0f/%.0f MB  %.0f KB/s"
                            % (pct, got / 1048576, total / 1048576, speed))
                        last = pct
        return dst.stat().st_size > 0
    except Exception as exc:  # noqa: BLE001
        log("  失败：%s: %s" % (type(exc).__name__, str(exc)[:120]))
        dst.unlink(missing_ok=True)
        return False


def _fetch(cfg: dict) -> bool:
    dest = Path(cfg["dest"])
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / (cfg["name"] + ".tar.bz2")
    for proxy in PROXIES:
        if _download(proxy + GH.format(tag=cfg["tag"], name=cfg["name"]), tmp):
            break
    else:
        log("  所有源都失败。可手动下载后解压到 %s：" % dest)
        log("    https://github.com/k2-fsa/sherpa-onnx/releases/tag/%s" % cfg["tag"])
        return False

    log("  解压中 ...")
    try:
        with tarfile.open(tmp, "r:bz2") as tf:
            _safe_extract(tf, dest)
    except (tarfile.TarError, ValueError) as exc:
        tmp.unlink(missing_ok=True)
        log("  压缩包无效：%s" % exc)
        return False
    tmp.unlink(missing_ok=True)

    inner = dest / cfg["name"]  # 压缩包自带一层目录，展平
    if inner.is_dir():
        for name in os.listdir(inner):
            shutil.move(str(inner / name), str(dest / name))
        inner.rmdir()

    log("  完成：%s" % dest)
    return _ready(cfg)


def _auto_source() -> Path | None:
    env = os.environ.get("SHERPA_SOURCE_MODELS")
    if env and Path(env).is_dir():
        return Path(env)
    # 同级目录下的 voice_assistant/models（与「语音」项目共用）
    sibling = ROOT.parent / "voice_assistant" / "models"
    if sibling.is_dir():
        return sibling
    return None


def prepare_vad(source=None, force=False):
    target = MODELS_DIR / 'vad' / 'silero_vad.onnx'
    if target.is_file() and not force and hashlib.sha256(target.read_bytes()).hexdigest() == VAD_SHA256:
        log('[vad] 已就绪')
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_suffix('.download')
    origin = source / 'vad' / target.name if source else None
    if origin is not None and origin.is_file():
        shutil.copy2(origin, pending)
    elif not _download(VAD_URL, pending):
        return False
    if hashlib.sha256(pending.read_bytes()).hexdigest() != VAD_SHA256:
        log('[vad] 校验不符，保留已有模型；请核对官方模型版本')
        pending.unlink(missing_ok=True)
        return False
    pending.replace(target)
    log('[vad] 人声检测模型已就绪')
    return True


def main() -> int:
    args = sys.argv[1:]
    force = "--force" in args
    src_arg = None
    if "--from" in args:
        src_arg = args[args.index("--from") + 1]
    only = None
    if "--kws-only" in args:
        only = "kws"
    if "--asr-only" in args:
        only = "asr"

    keys = [only] if only else ["kws", "asr"]
    source = Path(src_arg) if src_arg else _auto_source()
    mode = "copy from %s" % source if source else "download"
    log("准备 sherpa-onnx 模型（%s）：%s\n" % (", ".join(keys), mode))

    rc = 0
    for key in keys:
        cfg = SPECS[key]
        if _ready(cfg) and not force:
            log("[%s] 已就绪，跳过：%s" % (key, cfg["dest"]))
            continue
        ok = _copy_from(source, cfg) if source else False
        if not ok and not source:
            ok = _fetch(cfg)
        elif not ok:
            log("[%s] 从 %s 复制失败，改用下载" % (key, source))
            ok = _fetch(cfg)
        if not ok:
            rc = 1

    if only is None and not prepare_vad(source, force):
        rc = 1

    # 生成 keywords.txt（有 tokens.txt 和 keywords_raw.txt 时）
    if "--no-keywords" not in args:
        raw = MODELS_DIR / "kws" / "keywords_raw.txt"
        tokens = MODELS_DIR / "kws" / "tokens.txt"
        if raw.exists() and tokens.exists():
            log("\n生成唤醒词表 ...")
            try:
                import subprocess
                subprocess.run([sys.executable, str(ROOT / "scripts" / "make_keywords.py")], check=False)
            except Exception as exc:  # noqa: BLE001
                log("自动生成唤醒词失败：%s（可手动运行 scripts/make_keywords.py）" % exc)

    log("\n完成。校验：.venv/bin/python scripts/pi_doctor.py")
    return rc


if __name__ == "__main__":
    sys.exit(main())
