"""读取、验证剧本；配置错误应在播放/连接硬件前暴露。"""
import json
import math
import unicodedata
from pathlib import Path

from paths import find_audio

DEFAULT_SCRIPT = Path(__file__).with_name('queen_dialog.json')
DANCES = ('act1', 'act2', 'act3', 'act4', 'act5')


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).lower() if c.isalnum())


def load_script(path=None):
    with open(path or DEFAULT_SCRIPT, encoding='utf-8-sig') as handle:
        script = json.load(handle)
    validate_script(script)
    return script


def validate_script(script):
    if not isinstance(script, dict):
        raise ValueError('剧本必须是 JSON 对象')
    states = script.get('states')
    timing = script.get('timing')
    if not isinstance(states, dict) or not states or not isinstance(timing, dict):
        raise ValueError('缺少 states / timing')
    if script.get('initial') not in states or 'ENDING' not in states or 'ERROR' in states:
        raise ValueError('初始状态、ENDING 或保留状态 ERROR 不合法')
    from utterance import listening_settings
    listening_settings(script.get('listening'))
    for name in ('vision_first_seconds', 'vision_change_seconds',
                 'audio_timeout_seconds', 'dance_timeout_seconds'):
        value = timing.get(name)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0 or value > 3600):
            raise ValueError('时间配置不合法：%s' % name)
        if name not in ('vision_first_seconds', 'vision_change_seconds') and value == 0:
            raise ValueError('时间必须大于零：%s' % name)

    def validate_steps(steps):
        if not isinstance(steps, list):
            raise ValueError('steps 必须是列表')
        for step in steps:
            if not isinstance(step, dict) or len(step) != 1:
                raise ValueError('每个 step 必须且只能有一个操作')
            key, value = next(iter(step.items()))
            if key in ('audio', 'dance'):
                if not isinstance(value, str) or not find_audio(value):
                    raise ValueError('音频不存在：%s' % value)
                if key == 'dance' and value not in DANCES:
                    raise ValueError('未知舞蹈：%s' % value)
            elif key == 'wait_setting':
                if not isinstance(value, str) or value not in timing:
                    raise ValueError('未知时间配置：%s' % value)
            elif key == 'notice':
                if not isinstance(value, str) or not value.strip():
                    raise ValueError('notice 必须是非空文本')
            else:
                raise ValueError('未知操作：%s' % key)

    validate_steps(script.get('startup', []))
    for name, node in states.items():
        if not isinstance(node, dict) or not isinstance(node.get('prompt'), str):
            raise ValueError('节点缺少 prompt：%s' % name)
        validate_steps(node.get('steps'))
        if name == 'ENDING':
            if node.get('next') is not None or node['steps'] or node.get('auto'):
                raise ValueError('ENDING 必须是无动作终点')
            continue
        if not isinstance(node.get('next'), str) or node['next'] not in states:
            raise ValueError('节点目标不存在：%s' % name)
        if 'auto' in node and not isinstance(node['auto'], bool):
            raise ValueError('auto 必须是布尔值：%s' % name)
        if not node.get('auto'):
            keywords = node.get('keywords')
            if (not isinstance(keywords, list) or not keywords
                    or any(not isinstance(k, str) or not normalize(k) for k in keywords)):
                raise ValueError('交互节点必须有有效关键词：%s' % name)
    # 每个节点都必须最终抵达 ENDING，阻止自动循环或无出口的配置。
    for name in states:
        seen = set()
        current = name
        while current != 'ENDING':
            if current in seen:
                raise ValueError('剧本状态形成循环：%s' % current)
            seen.add(current)
            current = states[current]['next']
    demo = script.get('demo_inputs')
    if not isinstance(demo, list) or any(not isinstance(s, str) for s in demo):
        raise ValueError('demo_inputs 必须是文本列表')
    return script
