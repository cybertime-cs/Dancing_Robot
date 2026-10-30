"""独立排练的动作清单；仅接受清单中的动作，不发送任意文件名。"""
from pathlib import Path
import json
import re
from paths import find_audio


def load_actions():
    with Path(__file__).with_name('actions.json').open(encoding='utf-8') as handle:
        actions = json.load(handle)
    ids = set()
    for action in actions:
        if action['id'] in ids or not re.fullmatch(r'[A-Za-z0-9]+\.(bin|odr)', action['file']):
            raise ValueError('重复动作或非法动作文件名：%s' % action)
        ids.add(action['id'])
        if find_audio(action['audio']) is None:
            raise ValueError('动作音频不存在：%s' % action['audio'])
        if type(action['parallel_audio']) is not bool or not 0 < action['timeout_seconds'] <= 3600:
            raise ValueError('动作设置无效：%s' % action['id'])
    return actions


def get_action(name):
    for item in load_actions():
        if name in (item['id'], item['label']):
            return item
    raise ValueError('未知动作：%s；用 --list-actions 查看清单' % name)
