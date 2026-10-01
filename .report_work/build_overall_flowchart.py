from pathlib import Path
from dataclasses import dataclass
from html import escape
import json
import math

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import toColor


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports' / '机器人软件总体流程'
OUT.mkdir(parents=True, exist_ok=True)
W, H, SCALE = 2240, 2470, 2
FONT = r'C:\Windows\Fonts\msyh.ttc'
BOLD = r'C:\Windows\Fonts\msyhbd.ttc'
pdfmetrics.registerFont(TTFont('YaHei', FONT, subfontIndex=0))
pdfmetrics.registerFont(TTFont('YaHeiBold', BOLD, subfontIndex=0))
INK, MUTED, LINE = '#20344B', '#627389', '#6C7B8F'
BLUE, GREEN, ORANGE, PURPLE = '#256395', '#237B68', '#B27522', '#7552A0'
commands = []
nodes = {}
edges = []
labels = []
font_cache = {}


def font(size, bold=False, scale=1):
    key = (size, bold, scale)
    if key not in font_cache:
        font_cache[key] = ImageFont.truetype(BOLD if bold else FONT, round(size * scale))
    return font_cache[key]


def add(kind, layer=3, **values):
    commands.append(dict(kind=kind, layer=layer, **values))


def text(x, y, value, size=30, color=INK, bold=False, anchor='middle', layer=4):
    add('text', layer, x=x, y=y, value=value, size=size, color=color,
        bold=bold, anchor=anchor)


def rect(x, y, w, h, fill='white', stroke='#D8E2EC', radius=16,
         width=2, dashed=False, layer=3):
    add('rect', layer, x=x, y=y, w=w, h=h, fill=fill, stroke=stroke,
        radius=radius, width=width, dashed=dashed)


@dataclass
class Node:
    id: str
    cx: float
    cy: float
    w: float
    h: float
    lines: str
    shape: str = 'rect'
    color: str = LINE
    fill: str = 'white'
    size: int = 32
    dashed: bool = False
    bold: bool = False

    def port(self, side):
        return {'t': (self.cx, self.cy - self.h / 2),
                'b': (self.cx, self.cy + self.h / 2),
                'l': (self.cx - self.w / 2, self.cy),
                'r': (self.cx + self.w / 2, self.cy)}[side]

    def draw(self):
        if self.shape == 'diamond':
            add('polygon', points=[self.port(s) for s in ('t', 'r', 'b', 'l')],
                fill=self.fill, stroke=self.color, width=2.4, dashed=self.dashed)
        else:
            rect(self.cx - self.w/2, self.cy - self.h/2, self.w, self.h,
                 fill=self.fill, stroke=self.color,
                 radius=self.h/2 if self.shape == 'pill' else 14,
                 dashed=self.dashed, width=2.4)
        lines = self.lines.split('\n')
        leading = self.size * 1.28
        for i, line in enumerate(lines):
            dy = (i - (len(lines)-1)/2) * leading
            width = font(self.size, self.bold).getlength(line)
            if self.shape == 'diamond':
                available = self.w * (1 - (abs(dy) + self.size * .48)/(self.h/2)) - 18
            else:
                available = self.w - 26
            assert width <= available, (self.id, line, round(width), round(available))
            text(self.cx, self.cy + dy, line, self.size, bold=self.bold)


def node(id, cx, cy, w, h, lines, **kwargs):
    n = Node(id, cx, cy, w, h, lines, **kwargs)
    assert id not in nodes
    nodes[id] = n
    return n


def edge(src, dst, points=None, s='b', t='t', label=None, label_at=None,
         color=LINE, dashed=False, arrow=True, width=3):
    start = nodes[src].port(s) if src else None
    finish = nodes[dst].port(t) if dst else None
    pts = ([start] if start else []) + (points or []) + ([finish] if finish else [])
    assert len(pts) >= 2
    for a, b in zip(pts, pts[1:]):
        assert a[0] == b[0] or a[1] == b[1], ('nonorthogonal edge', src, dst, a, b)
    edges.append(dict(src=src, dst=dst, points=pts, label=label))
    add('polyline', 2, points=pts, color=color, dashed=dashed, arrow=arrow, width=width)
    if label:
        assert label_at
        labels.append((label_at[0], label_at[1], label, color))


# Header and the four mode lanes.
rect(0, 0, W, H, fill='white', stroke='white', radius=0, width=0, layer=0)
rect(65, 55, 9, 63, fill=BLUE, stroke=BLUE, radius=4, width=0, layer=1)
text(100, 75, '机器人软件总体流程', 51, bold=True, anchor='start')
text(100, 128, '树莓派主控  ·  本地识别与交互  ·  串口动作执行', 28,
     color=MUTED, anchor='start')

lanes = [(65, 305, '语音动作', BLUE, '#F3F7FC'),
         (605, 845, '姿态识别', GREEN, '#F3F9F6'),
         (1145, 1385, '韵律识别', ORANGE, '#FCF8F0'),
         (1685, 1925, '人机交互', PURPLE, '#F8F5FC')]
for x, cx, name, color, fill in lanes:
    rect(x, 600, 490, 1550, fill=fill, stroke='#DCE5EE', radius=23,
         width=2, dashed=False, layer=1)
    rect(x+22, 630, 5, 34, fill=color, stroke=color, radius=2, width=0, layer=1)
    text(x+45, 647, name, 35, bold=True, color=color, anchor='start')

# Startup and mode selection: the serial port is opened before keyword matching.
node('start', 155, 267, 150, 74, '启动', shape='pill', color=BLUE, fill='#EDF4FC', bold=True)
node('init', 421, 267, 310, 126, '加载离线语音模型\n初始化姿态识别器', color=BLUE, size=31)
node('wake', 741, 267, 270, 140, '检测到\n唤醒词？', shape='diamond', color=BLUE, size=29)
node('release', 1080, 267, 346, 126, '释放唤醒录音流\n提示录入功能指令', color=BLUE)
node('asr', 1445, 267, 320, 126, '采集语音并转写\nVosk：输出文本', color=BLUE)
node('serial', 1889, 267, 464, 126, '读取关键词配置\n初始化串口（115200）', color=BLUE)
node('mode', 1120, 446, 372, 140, '匹配到\n功能指令？', shape='diamond', color=BLUE, size=30)
node('invalid', 1960, 499, 352, 82, '播报未识别提示', color=LINE, size=31)
node('finish', 1120, 2286, 452, 84, '本轮任务处理返回', shape='pill', color=BLUE,
     fill='#EDF4FC', bold=True, size=34)
edge('start', 'init', s='r', t='l')
edge('init', 'wake', s='r', t='l')
edge('wake', 'wake', s='t', t='l', points=[(741, 174), (603, 174), (603, 267)],
     label='否', label_at=(773, 183))
text(741, 340, 'Snowboy 热词检测', 23, color=MUTED)
edge('wake', 'release', s='r', t='l', label='是', label_at=(882, 241))
edge('release', 'asr', s='r', t='l')
edge('asr', 'serial', s='r', t='l')
edge('serial', 'mode', points=[(1889, 370), (1120, 370)])
edge('mode', 'invalid', s='r', t='t', points=[(1960, 446)],
     label='否', label_at=(1360, 421))
edge('invalid', 'finish', points=[(1960, 562), (2205, 562), (2205, 2213), (1120, 2213)])
edge('mode', None, points=[(1120, 565)], arrow=False,
     label='是', label_at=(1151, 541))
edge(None, None, points=[(305, 565), (1925, 565)], arrow=False, width=3.2)

# Voice action: bounded retries, user exit, serial feedback and the success loop.
node('v_input', 305, 753, 350, 108, '提示并采集动作指令\nVosk 转写为文本', color=BLUE, size=31)
node('v_exit', 305, 910, 350, 140, '包含动作模式\n退出指令？', shape='diamond', color=BLUE, size=28)
node('v_map', 305, 1080, 350, 102, '按指令词表匹配\n跳过黑名单类别', color=BLUE)
node('v_valid', 305, 1254, 350, 136, '匹配到\n有效动作？', shape='diamond', color=BLUE, size=30)
node('v_execute', 305, 1420, 350, 108, '动作映射与提示\n串口下发并等待返回¹', color=BLUE, size=30)
node('v_reset', 305, 1581, 350, 102, '连续失败计数清零\n提示继续输入', color=BLUE, size=31)
node('v_fail', 305, 1750, 350, 108, '播放未匹配提示\n连续失败次数加 1', color=BLUE)
node('v_limit', 305, 1915, 350, 136, '连续失败\n达到 3 次？', shape='diamond', color=BLUE, size=30)
node('v_end', 305, 2076, 330, 70, '退出语音动作模式', shape='pill', color=BLUE, size=30)
edge(None, 'v_input', points=[(305, 565)], color=BLUE,
     label='计数置零', label_at=(390, 681))
edge('v_input', 'v_exit', color=BLUE)
edge('v_exit', 'v_map', color=BLUE, label='否', label_at=(337, 1004))
edge('v_exit', 'v_end', s='r', points=[(529, 910), (529, 2018), (305, 2018)],
     color=BLUE, label='是', label_at=(508, 882))
edge('v_map', 'v_valid', color=BLUE)
edge('v_valid', 'v_execute', color=BLUE, label='是', label_at=(337, 1340))
edge('v_valid', 'v_fail', s='r', t='r', points=[(500, 1254), (500, 1750)],
     color=BLUE, label='否', label_at=(500, 1220))
edge('v_execute', 'v_reset', color=BLUE)
edge('v_reset', 'v_input', s='l', t='l', points=[(101, 1581), (101, 753)], color=BLUE)
edge('v_fail', 'v_limit', color=BLUE)
edge('v_limit', 'v_input', s='l', t='l', points=[(101, 1915), (101, 753)], color=BLUE,
     label='否', label_at=(105, 1886))
edge('v_limit', 'v_end', s='r', points=[(529, 1915), (529, 2018), (305, 2018)],
     color=BLUE, label='是', label_at=(508, 1886))

# Pose: reset the stability clock on changing/missing labels; bound acquisition.
node('p_prepare', 845, 753, 350, 108, '准备动作与提示\n调用姿态识别器', color=GREEN)
node('p_frame', 845, 942, 350, 156,
     '图像采集与方向校正\nMediaPipe 提取关键点\n二维特征输入姿态分类器\n类别变化或丢失则重新计时', color=GREEN, size=27)
node('p_timeout', 845, 1126, 364, 142, '超过 15 秒\n或图像不可用？',
     shape='diamond', color=GREEN, size=27)
node('p_stable', 845, 1301, 350, 140, '同一姿态\n稳定 2 秒？', shape='diamond', color=GREEN, size=30)
node('p_return', 845, 1470, 350, 104, '执行复位动作\n获得稳定姿态标签', color=GREEN)
node('p_stop', 845, 1644, 350, 136, '识别到\n停止姿态？', shape='diamond', color=GREEN, size=30)
node('p_execute', 845, 1822, 350, 112, '姿态映射与语音提示\n下发 .bin 并等待返回¹', color=GREEN, size=30)
node('p_end', 845, 2076, 350, 94, '复位并播放提示\n退出姿态模式', shape='pill', color=GREEN, size=30)
edge(None, 'p_prepare', points=[(845, 565)], color=GREEN)
edge('p_prepare', 'p_frame', color=GREEN)
edge('p_frame', 'p_timeout', color=GREEN)
edge('p_timeout', 'p_end', s='r', points=[(1064, 1126), (1064, 2006), (845, 2006)],
     color=GREEN, label='是', label_at=(1042, 1096))
edge('p_timeout', 'p_stable', color=GREEN, label='否', label_at=(877, 1213))
edge('p_stable', 'p_frame', s='l', t='l', points=[(645, 1301), (645, 942)],
     color=GREEN, label='否', label_at=(650, 1268))
edge('p_stable', 'p_return', color=GREEN, label='是', label_at=(877, 1398))
edge('p_return', 'p_stop', color=GREEN)
edge('p_stop', 'p_end', s='r', points=[(1064, 1644), (1064, 2006), (845, 2006)],
     color=GREEN, label='是', label_at=(1042, 1614))
edge('p_stop', 'p_execute', color=GREEN, label='否', label_at=(877, 1738))
edge('p_execute', 'p_prepare', s='l', t='l', points=[(620, 1822), (620, 753)], color=GREEN)

# The new rhythm recognizer is verified independently; all its paths are dashed.
node('r_input', 1385, 753, 350, 108, '输入 15 秒短音频\n加载离线参考特征库', color=ORANGE, size=31, dashed=True)
node('r_features', 1385, 978, 350, 178,
     '转为 8 kHz 单声道\n四频段能量变化特征\n特征步长 32 ms\n8 秒滑窗相关比较', color=ORANGE, size=31, dashed=True)
node('r_gate', 1385, 1210, 372, 180, '得分 ≥ 0.45\n且领先差值\n≥ 0.10？',
     shape='diamond', color=ORANGE, size=28, dashed=True)
node('r_match', 1385, 1410, 350, 108, '输出匹配曲目\n映射舞蹈动作文件', color=ORANGE, dashed=True)
node('r_send', 1385, 1605, 350, 108, '封装 .odr 指令\n串口下发舞蹈序列', color=ORANGE, dashed=True)
node('r_play', 1385, 1793, 350, 108, '播放对应歌曲\n机器人执行舞蹈', color=ORANGE, dashed=True)
node('r_unknown', 1385, 1954, 350, 78, '返回“未识别”', color=ORANGE, size=31, dashed=True)
node('r_end', 1385, 2076, 350, 70, '本轮韵律流程结束', shape='pill', color=ORANGE, size=30, dashed=True)
edge(None, 'r_input', points=[(1385, 565)], color=ORANGE, dashed=True)
edge('r_input', 'r_features', color=ORANGE, dashed=True)
edge('r_features', 'r_gate', color=ORANGE, dashed=True)
edge('r_gate', 'r_match', color=ORANGE, dashed=True, label='是', label_at=(1417, 1310))
edge('r_gate', 'r_unknown', s='r', t='r', points=[(1610, 1210), (1610, 1954)],
     color=ORANGE, dashed=True, label='否', label_at=(1594, 1178))
edge('r_match', 'r_send', color=ORANGE, dashed=True)
edge('r_send', 'r_play', color=ORANGE, dashed=True)
# Successful dancing bypasses the unknown-result node.
edge('r_play', 'r_end', s='l', points=[(1179, 1793), (1179, 2024), (1385, 2024)],
     color=ORANGE, dashed=True)
edge('r_unknown', 'r_end', color=ORANGE, dashed=True)

# Dialogue: no conversation history, no concurrent speech generation/playback.
node('d_input', 1925, 753, 350, 108, '提示提问并采集语音\nVosk 输出问题文本', color=PURPLE, size=31)
node('d_exit', 1925, 919, 350, 138, '包含“结束”\n或“退出”？', shape='diamond', color=PURPLE, size=28)
node('d_query', 1925, 1088, 350, 128, 'Ollama 本地接口\n127.0.0.1:11434\nqwen:0.5b 单轮生成', color=PURPLE, size=28)
node('d_chunk', 1925, 1251, 350, 108, '顺序接收文本块\n清理 *、# 并缓存', color=PURPLE, size=31)
node('d_segment', 1925, 1418, 370, 160, '句末标点或\n缓存长度 > 30？', shape='diamond', color=PURPLE, size=27)
node('d_speak', 1925, 1583, 350, 102, 'eSpeak 中文播报\n播报完成后继续处理', color=PURPLE, size=30)
node('d_done', 1925, 1750, 350, 136, '流式响应\n已结束？', shape='diamond', color=PURPLE, size=30)
node('d_tail', 1925, 1915, 350, 108, '播报末尾缓存\n继续下一轮提问', color=PURPLE)
node('d_end', 1925, 2076, 330, 70, '退出人机交互模式', shape='pill', color=PURPLE, size=30)
edge(None, 'd_input', points=[(1925, 565)], color=PURPLE)
edge('d_input', 'd_exit', color=PURPLE)
edge('d_exit', 'd_query', color=PURPLE, label='否', label_at=(1957, 1010))
edge('d_exit', 'd_end', s='r', points=[(2154, 919), (2154, 2018), (1925, 2018)],
     color=PURPLE, label='是', label_at=(2128, 889))
edge('d_query', 'd_chunk', color=PURPLE)
edge('d_chunk', 'd_segment', color=PURPLE)
edge('d_segment', 'd_speak', color=PURPLE, label='是', label_at=(1957, 1506))
edge('d_segment', 'd_done', s='l', t='l', points=[(1737, 1418), (1737, 1750)],
     color=PURPLE, label='否', label_at=(1737, 1389))
edge('d_speak', 'd_done', color=PURPLE)
edge('d_done', 'd_chunk', s='r', t='r', points=[(2126, 1750), (2126, 1251)],
     color=PURPLE, label='否', label_at=(2127, 1720))
edge('d_done', 'd_tail', color=PURPLE, label='是', label_at=(1957, 1846))
edge('d_tail', 'd_input', s='l', t='l', points=[(1710, 1915), (1710, 753)], color=PURPLE)

# All mode returns merge into the current task return, not a restart of Snowboy.
for id, cx, color, dashed in [('v_end',305,BLUE,False), ('p_end',845,GREEN,False),
                               ('r_end',1385,ORANGE,True), ('d_end',1925,PURPLE,False)]:
    edge(id, None, points=[(cx, 2180)], color=color, dashed=dashed, arrow=False)
edge(None, None, points=[(305, 2180), (1925, 2180)], arrow=False)
edge(None, 'finish', points=[(1120, 2180)])
add('circle', 3, cx=1120, cy=2180, radius=5, fill=LINE)
add('circle', 3, cx=1120, cy=2213, radius=5, fill=LINE)

# Draw all four modes uniformly as the overall software design.
for n in nodes.values():
    n.dashed = False
for c in commands:
    if 'dashed' in c:
        c['dashed'] = False

# Two compact technical notes, without figure numbering or progress labels.
text(83, 2386, '¹ 动作包包含文件名、类型、长度与校验值；语音和姿态动作等待规定回执，最长 200 秒。',
     25, color=MUTED, anchor='start')
text(83, 2430, '语音输入采用 16 kHz、单声道、PCM 16 bit；人机交互逐轮请求本地模型，分段播报。',
     25, color=MUTED, anchor='start')

for n in nodes.values():
    n.draw()
for x, y, label, color in labels:
    width = font(25).getlength(label) + 14
    rect(x-width/2, y-18, width, 36, fill='white', stroke='white', radius=6, width=0, layer=5)
    text(x, y, label, 25, color=color, layer=6)

# Geometric check: a connector may only touch its own source/target nodes.
for e in edges:
    for a, b in zip(e['points'], e['points'][1:]):
        for id, n in nodes.items():
            if id in (e['src'], e['dst']):
                continue
            x0, x1 = n.cx-n.w/2+4, n.cx+n.w/2-4
            y0, y1 = n.cy-n.h/2+4, n.cy+n.h/2-4
            if a[0] == b[0]:
                hit = x0 < a[0] < x1 and max(min(a[1],b[1]),y0) < min(max(a[1],b[1]),y1)
            else:
                hit = y0 < a[1] < y1 and max(min(a[0],b[0]),x0) < min(max(a[0],b[0]),x1)
            assert not hit, ('connector crosses unrelated node', e['src'], e['dst'], id)

commands.sort(key=lambda c:c['layer'])
im = Image.new('RGB', (W*SCALE,H*SCALE), 'white')
draw = ImageDraw.Draw(im)
pdf = canvas.Canvas(str(OUT/'机器人软件总体流程图.pdf'), pagesize=(W*.36,H*.36))
pdf.setTitle('机器人软件总体流程图')
pdf.setAuthor('启真队')
pdf.scale(.36,.36)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       '<title>机器人软件总体流程图</title>',
       '<desc>热词唤醒、功能选择、语音动作、姿态识别、韵律验证方案和本地人机交互。</desc>']


def spts(pts):
    return [(x*SCALE,y*SCALE) for x,y in pts]


def dash_segments(pts, on=11, off=8):
    for a,b in zip(pts,pts[1:]):
        length=math.dist(a,b)
        if not length:
            continue
        for start in range(0,math.ceil(length),on+off):
            stop=min(length,start+on)
            yield ((a[0]+(b[0]-a[0])*start/length,a[1]+(b[1]-a[1])*start/length),
                   (a[0]+(b[0]-a[0])*stop/length,a[1]+(b[1]-a[1])*stop/length))


def pdfpoly(pts, color, width, fill=None, dashed=False, close=False):
    p=pdf.beginPath()
    p.moveTo(pts[0][0],H-pts[0][1])
    for x,y in pts[1:]: p.lineTo(x,H-y)
    if close: p.close()
    pdf.setStrokeColor(toColor(color))
    pdf.setLineWidth(width)
    pdf.setDash(11,8) if dashed else pdf.setDash()
    if fill: pdf.setFillColor(toColor(fill))
    pdf.drawPath(p,stroke=int(width>0),fill=int(fill is not None))


for c in commands:
    kind=c['kind']
    if kind=='rect':
        x,y,w,h=c['x'],c['y'],c['w'],c['h']
        draw.rounded_rectangle((x*SCALE,y*SCALE,(x+w)*SCALE,(y+h)*SCALE),
                               radius=c['radius']*SCALE,fill=c['fill'],
                               outline=None if c['dashed'] or not c['width'] else c['stroke'],
                               width=max(1,round(c['width']*SCALE)))
        if c['dashed']:
            # Dashed line, with short rounded corners preserved in the PDF/SVG.
            perimeter=[(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]
            for a,b in dash_segments(perimeter):
                draw.line(spts([a,b]),fill=c['stroke'],width=max(1,round(c['width']*SCALE)))
        pdf.setStrokeColor(toColor(c['stroke']))
        pdf.setFillColor(toColor(c['fill']))
        pdf.setLineWidth(c['width'])
        pdf.setDash(11,8) if c['dashed'] else pdf.setDash()
        pdf.roundRect(x,H-y-h,w,h,c['radius'],stroke=int(c['width']>0),fill=1)
        sd=' stroke-dasharray="11 8"' if c['dashed'] else ''
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{c["radius"]}" fill="{c["fill"]}" stroke="{c["stroke"]}" stroke-width="{c["width"]}"{sd}/>')
    elif kind in ('polyline','polygon'):
        pts=c['points']
        color=c.get('color',c.get('stroke'))
        width=c['width']
        if kind=='polygon':
            draw.polygon(spts(pts),fill=c['fill'])
            pts=pts+[pts[0]]
        if c['dashed']:
            for a,b in dash_segments(pts): draw.line(spts([a,b]),fill=color,width=round(width*SCALE))
        else:
            draw.line(spts(pts),fill=color,width=round(width*SCALE),joint='curve')
        pdfpoly(pts,color,width,c.get('fill'),c['dashed'],kind=='polygon')
        tag='polygon' if kind=='polygon' else 'polyline'
        points=' '.join(f'{x},{y}' for x,y in (pts[:-1] if kind=='polygon' else pts))
        sd=' stroke-dasharray="11 8"' if c['dashed'] else ''
        svg.append(f'<{tag} points="{points}" fill="{c.get("fill","none")}" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"{sd}/>')
        if c.get('arrow'):
            a,b=next((a,b) for a,b in reversed(list(zip(pts,pts[1:]))) if a!=b)
            angle=math.atan2(b[1]-a[1],b[0]-a[0])
            tip=[b,(b[0]-12*math.cos(angle)+5.5*math.sin(angle),b[1]-12*math.sin(angle)-5.5*math.cos(angle)),
                   (b[0]-12*math.cos(angle)-5.5*math.sin(angle),b[1]-12*math.sin(angle)+5.5*math.cos(angle))]
            draw.polygon(spts(tip),fill=color)
            pdfpoly(tip,color,0,color,close=True)
            svg.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in tip)+f'" fill="{color}"/>')
    elif kind=='circle':
        x,y,r=c['cx'],c['cy'],c['radius']
        draw.ellipse(((x-r)*SCALE,(y-r)*SCALE,(x+r)*SCALE,(y+r)*SCALE),fill=c['fill'])
        pdf.setFillColor(toColor(c['fill']))
        pdf.circle(x,H-y,r,stroke=0,fill=1)
        svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c["fill"]}"/>')
    elif kind=='text':
        x,y=c['x'],c['y']
        f=font(c['size'],c['bold'],SCALE)
        bbox=draw.textbbox((0,0),c['value'],font=f)
        tw=draw.textlength(c['value'],font=f)
        tx=x*SCALE - (tw/2 if c['anchor']=='middle' else tw if c['anchor']=='end' else 0)
        ty=y*SCALE-(bbox[1]+bbox[3])/2
        draw.text((tx,ty),c['value'],font=f,fill=c['color'])
        family='YaHeiBold' if c['bold'] else 'YaHei'
        pdf.setFont(family,c['size'])
        pdf.setFillColor(toColor(c['color']))
        pw=pdfmetrics.stringWidth(c['value'],family,c['size'])
        px=x-(pw/2 if c['anchor']=='middle' else pw if c['anchor']=='end' else 0)
        pdf.drawString(px,H-y-c['size']*.36,c['value'])
        weight='700' if c['bold'] else '400'
        svg.append(f'<text x="{x}" y="{y}" text-anchor="{c["anchor"]}" dominant-baseline="central" font-family="Microsoft YaHei, SimHei, sans-serif" font-size="{c["size"]}" font-weight="{weight}" fill="{c["color"]}">{escape(c["value"])}</text>')

svg.append('</svg>')
pdf.showPage()
pdf.save()
im.save(OUT/'机器人软件总体流程图.png',dpi=(300,300),optimize=True)
(OUT/'机器人软件总体流程图.svg').write_text('\n'.join(svg),encoding='utf-8')
qa=ROOT/'.report_work'/'overall-flow-preview.png'
preview=im.copy()
preview.thumbnail((1400,1600),Image.Resampling.LANCZOS)
preview.save(qa)
(ROOT/'.report_work'/'overall-flow-structure.json').write_text(json.dumps({
    'nodes':{k:n.__dict__ for k,n in nodes.items()}, 'edges':edges,
    'note':'Overall software design with four modes. No automatic hotword-stream restart is drawn.'
},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'outputs':[str(p) for p in OUT.iterdir()],
                  'nodes':len(nodes),'edges':len(edges),'image_pixels':im.size},ensure_ascii=False))
