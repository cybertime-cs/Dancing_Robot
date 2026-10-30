#!/usr/bin/env python3
"""更新剧本 DOCX 文本，同时保留全部格式与图片。"""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent
docx = root / "银河号剧情+(1).docx"
temporary = docx.with_suffix(".tmp.docx")

with ZipFile(docx, "r") as source, ZipFile(temporary, "w", ZIP_DEFLATED) as target:
    for item in source.infolist():
        content = source.read(item.filename)
        if item.filename.endswith((".xml", ".rels")):
            replacements = {
                "黄河": "银河",
                "音乐动作1": "动作1.mp3",
                "音乐动作2": "动作2.mp3",
                "音乐动作3": "动作3.mp3",
                "音乐动作4": "动作4.mp3",
                "音乐动作5": "动作5.mp3",
                "音乐动作6": "动作6.mp3",
            }
            for old, new in replacements.items():
                content = content.replace(old.encode(), new.encode())
        target.writestr(item, content)

temporary.replace(docx)
print(f"已更新：{docx.name}")
