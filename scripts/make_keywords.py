#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文唤醒词 -> sherpa-onnx KWS 模型认识的 token 序列（拼音声母 + 韵母）。

改唤醒词只需要两步：
    1. 编辑 models/kws/keywords_raw.txt（每行一个中文词）
    2. 运行：python scripts/make_keywords.py

为什么不用 sherpa-onnx 自带的 text2token：
    a. 它内部无条件 import sentencepiece，虽然 ppinyin 模式根本用不到；
    b. 遇到词表外 token 时整行丢弃，但拼接 "@原词" 仍按原始行号，第一个词被丢
       之后所有标签会错位。
这里直接用 pypinyin 做转换，逻辑与官方 utils.to_pinyin 一致，但会明确报出
哪个 token 不在词表里。

依赖：pypinyin（python -m pip install pypinyin）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KWS_DIR = ROOT / "models" / "kws"
RAW_FILE = KWS_DIR / "keywords_raw.txt"
OUT_FILE = KWS_DIR / "keywords.txt"
TOKENS_FILE = KWS_DIR / "tokens.txt"


def load_tokens(path: Path) -> set:
    tokens = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) == 2:
            tokens.add(parts[0])
    return tokens


def to_ppinyin(word: str) -> list:
    """中文 -> [声母, 韵母(带声调), ...]，例如 小智小智 -> [x, iǎo, zh, ì, x, iǎo, zh, ì]"""
    from pypinyin import pinyin
    from pypinyin.contrib.tone_convert import to_finals_tone, to_initials

    out: list = []
    for one_pinyin in (x[0] for x in pinyin(word)):
        initial = to_initials(one_pinyin, strict=False)
        final = to_finals_tone(one_pinyin, strict=False)
        if not initial and not final:  # 非中文（数字、字母等）原样保留
            out.append(one_pinyin)
            continue
        if initial:
            out.append(initial)
        if final:
            out.append(final)
    return out


def parse_line(line: str):
    """拆成 (中文唤醒词, 额外信息如 :加分 / #阈值 / @原词)"""
    word = line.strip()
    if not word or word.startswith("#"):
        return None
    extra = [t for t in word.split() if t[0] in ":#@"]
    body = [t for t in word.split() if t[0] not in ":#@"]
    if not body:
        return None
    head = body[0]
    if not any(t.startswith("@") for t in extra):
        extra.append("@" + head)  # 没写 @ 就自动补，否则 result.keyword 会返回一串拼音
    return head, extra


def main() -> None:
    raw_file = Path(sys.argv[1]) if len(sys.argv) > 1 else RAW_FILE
    out_file = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT_FILE

    if not raw_file.exists():
        sys.exit("找不到 %s\n请先运行 scripts/prepare_sherpa_models.py 准备模型目录。" % raw_file)
    if not TOKENS_FILE.exists():
        sys.exit("找不到 %s\nKWS 模型还没准备好，请先运行 scripts/prepare_sherpa_models.py。" % TOKENS_FILE)

    table = load_tokens(TOKENS_FILE)
    lines: list = []
    for raw_line in raw_file.read_text(encoding="utf-8").splitlines():
        parsed = parse_line(raw_line)
        if parsed is None:
            continue
        word, extra = parsed
        tokens = to_ppinyin(word)
        missing = [t for t in tokens if t not in table]
        if missing:
            print("[跳过] %s：以下 token 不在 tokens.txt 里 -> %s" % (word, missing))
            continue
        lines.append(" ".join(tokens + extra))

    if not lines:
        sys.exit("没有生成任何唤醒词，请检查 %s" % raw_file)

    # 必须固定写 LF：Windows 上默认会写成 CRLF，行尾的 \r 会被 sherpa 当成
    # token 的一部分，导致唤醒词静默失效（而且从日志里完全看不出来）。
    text = "\n".join(lines) + "\n"
    with open(out_file, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("已生成 %s（共 %d 个唤醒词）：\n" % (out_file, len(lines)))
    print(text)


if __name__ == "__main__":
    main()
