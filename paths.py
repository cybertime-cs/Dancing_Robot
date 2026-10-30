# paths.py
"""统一的项目路径解析。

所有资源访问都基于项目根目录，不再依赖当前工作目录。整理前代码里到处
是 "resources/xxx.MP3" 这样的相对路径，一旦从别的目录启动程序就会找不到
文件；这里把它们收敛到一处。

音频查找统一走 find_audio()，忽略大小写与扩展名差异，因此
resources/indexchoice.mp3、IndexChoice.MP3 都能被 "indexchoice" 命中。
它还会扫描 resources/ 的所有子目录（例如 resources/show/act/），
这样演出素材可以按用途分开放，不必全挤在 resources/ 顶层。
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RESOURCES_DIR = os.path.join(PROJECT_ROOT, "resources")
TEMP_RECORD_DIR = os.path.join(PROJECT_ROOT, "temp_record")

# 同一主文件名存在多个文件时，优先返回的顺序
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


def project_path(*parts):
    """拼出项目内的绝对路径，例如 project_path("models", "kws")。"""
    return os.path.join(PROJECT_ROOT, *parts)


def resource(*parts):
    """拼出 resources/ 内的绝对路径，例如 resource("ding.wav")。"""
    return os.path.join(RESOURCES_DIR, *parts)


def search_dirs(directories=None):
    """find_audio 依次查找的目录。

    顺序：resources/ 顶层 → 其下所有子目录（递归、按名字排序）→ 额外指定的目录。
    顶层排在最前，因此同名文件永远优先命中顶层，原有行为不受影响；
    演出素材按用途分开放（resources/show/act/ 等）也能被找到。
    """
    dirs = [RESOURCES_DIR]
    if os.path.isdir(RESOURCES_DIR):
        for base, subdirs, _files in os.walk(RESOURCES_DIR):
            subdirs.sort()
            for name in subdirs:
                dirs.append(os.path.join(base, name))
    return dirs + list(directories or ())


def find_audio(name, directories=None):
    """在 resources/ 中按“主文件名”查找音频，找不到返回 None。

    下列写法都能命中 resources/indexchoice.mp3：
        find_audio("indexchoice")
        find_audio("indexchoice.mp3")
        find_audio("IndexChoice.MP3")
        find_audio("resources/indexchoice.mp3")

    也会命中 resources/show/act/act1.MP3 这样的子目录音频。
    """
    if not name:
        return None
    base = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    stem = os.path.splitext(base)[0].lower()
    if not stem:
        return None
    wanted_ext = os.path.splitext(base)[1].lower().lstrip(".")

    matches = []
    for directory in search_dirs(directories):
        if not os.path.isdir(directory):
            continue
        for entry in sorted(os.listdir(directory)):
            entry_stem, entry_ext = os.path.splitext(entry)
            if entry_stem.lower() != stem:
                continue
            if wanted_ext and entry_ext.lower().lstrip(".") != wanted_ext:
                continue
            matches.append(os.path.join(directory, entry))

    if not matches:
        return None
    for ext in AUDIO_EXTS:
        for match in matches:
            if match.lower().endswith(ext):
                return match
    return matches[0]


def audio_exists(name):
    """资源音频是否存在。"""
    return find_audio(name) is not None


def ensure_temp_record_dir():
    """确保运行时临时录音目录存在，并返回其路径。"""
    os.makedirs(TEMP_RECORD_DIR, exist_ok=True)
    return TEMP_RECORD_DIR
