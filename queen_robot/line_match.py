"""当前节点的容错匹配，以及巡查独立入口的完整同音匹配。"""
from dataclasses import dataclass
from functools import lru_cache
import re
from .queen_script import normalize


@dataclass(frozen=True)
class Match:
    accepted: bool
    method: str = ''
    score: float = 0
    target: str = ''
    reason: str = ''


@lru_cache(maxsize=512)
def syllables(text):
    from pypinyin import lazy_pinyin, Style
    return tuple(lazy_pinyin(normalize(text), style=Style.NORMAL, errors=lambda chars: list(chars)))


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        following = [i]
        for j, y in enumerate(b, 1):
            following.append(min(following[-1] + 1, row[j] + 1, row[j-1] + (x != y)))
        row = following
    return row[-1]


def content(tokens):
    # 同一机器人名字的同音字自然归一；无需穷举“丰后、丰厚”等汉字。
    while tokens[:2] in (('feng', 'hou'), ('shou', 'dao')):
        tokens = tokens[2:]
    return tokens


def match_standalone_travel(text, node):
    """跨流程只接受完整指令；不继承普通节点的子串和近似容错。"""
    clean = normalize(text)
    if not clean or len(clean) > 160:
        return Match(False, reason='空白、非文字或内容过长')
    spoken = syllables(clean)
    # 可省略名字或使用其同音字，但不去掉“收到”等聊天前缀。
    if spoken[:2] == ('feng', 'hou'):
        spoken = spoken[2:]
    for target in (node['prompt'], '前往目标区域'):
        candidate = syllables(target)
        if candidate[:2] == ('feng', 'hou'):
            candidate = candidate[2:]
        if spoken and spoken == candidate:
            method = '精确' if clean == normalize(target) else '同音'
            return Match(True, method, 1, target)
    return Match(False, reason='跨流程巡查需要完整台词或“前往目标区域”')


def match_line(text, node):
    clean = normalize(text)
    if not clean or len(clean) > 160:
        return Match(False, reason='空白、非文字或内容过长')
    if any(word in clean for word in ('不要','取消','别执行','不执行','停止','别启动','不启动')):
        return Match(False, reason='检测到否定或停止表达')
    tokens = syllables(clean)
    prompt = normalize(node['prompt'])
    if len(clean) > max(12, int(len(prompt) * 1.3) + 4):
        return Match(False, reason='超出台词长度，可能混入其他说话声')
    best = Match(False, reason='不符合当前台词')
    keywords = node.get('keywords', [])
    # 剧本长句中的完整指令分句也可单独说，不能把任意聊天切开后挑关键词。
    clauses = [part for part in re.split(r'[，。！？,!?;；]', node['prompt'])
               if len(normalize(part)) >= 4 and any(normalize(k) in normalize(part) for k in keywords)]
    for target in [node['prompt'], *keywords, *clauses]:
        candidate = syllables(target)
        spoken = tokens
        # 仅名字节点：允许重复呼叫，但不接受聊天中提及名字。
        if candidate and not content(candidate):
            if spoken and not content(spoken) and spoken[:2] == ('feng','hou'):
                return Match(True, '同音', 1, target)
            continue
        spoken, candidate = content(spoken), content(candidate)
        if not candidate or not spoken:
            continue
        score = 1 - distance(spoken, candidate) / max(len(spoken), len(candidate))
        method = '同音' if spoken == candidate else '近似'
        if normalize(target) == clean:
            method = '精确'
        accepted = spoken == candidate
        # 长关键词可有少量前后修饰；短词只接受完整同音，降低聊天误触发。
        if not accepted and len(candidate) >= 4 and len(candidate) / len(spoken) >= .8:
            accepted = any(spoken[i:i+len(candidate)] == candidate for i in range(len(spoken)-len(candidate)+1))
            if accepted:
                method, score = '关键词', len(candidate) / len(spoken)
        if not accepted and min(len(spoken), len(candidate)) >= 7 and score >= .86:
            accepted = True
        if accepted and score > best.score:
            best = Match(True, method, score, target)
    return best
